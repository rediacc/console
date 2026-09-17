#!/usr/bin/env python3
"""Port of `.ci/scripts/private/renet-root-tests.sh`.

Runs the three `//go:build root` repository-state tests in `private/renet` and
refuses to report success unless each of them is seen to PASS by name.

WHY THE BY-NAME GUARD IS THE WHOLE SCRIPT. `go test` exits 0 for a run in which
every test SKIPPED, and it exits 0 for a `-run` pattern that matched nothing at
all. Either would make this a gate that passes without running. The twin
therefore greps its own captured output for `--- PASS: <name>` once per test and
exits 1 on the first one it cannot find, and that loop is reproduced here
exactly, including the fact that it reports only the FIRST missing test.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT: `go test`, once, with the twin's argv character for character. The
differential (`.ci/rediacc_ci/tests/test_private_renet_root_tests.py`) puts a
recording `go` on a scratch PATH and compares the argv both subjects produced,
because a port that printed the same transcript while running `go test` without
`-tags root` would pass a stdout-only comparison and test nothing: the three
subject tests do not even compile without that tag.

NOT SHELLED OUT: `grep`. `grep -q -- "--- PASS: $t"` is asking whether a byte
sequence occurs in a buffer the script already holds, and the three names carry
no regex metacharacters, so the pattern is a literal. The search is done on
BYTES rather than on a decoded string, which is what grep does, so output that
is not valid UTF-8 cannot change the verdict.

-----------------------------------------------------------------------------
COMMAND SUBSTITUTION IS AN OUTPUT FORMAT, NOT JUST A CAPTURE
-----------------------------------------------------------------------------
`out="$(go test ... 2>&1)"` then `echo "$out"` is NOT the same as letting go's
output through. It has three consequences and all three are visible to a caller:

  * go's stderr is folded into go's stdout, so nothing this script runs writes
    to the script's own stderr. The stderr stream carries only the two log lines.
  * `$()` strips ALL trailing newlines and `echo` then adds exactly one, so a go
    run ending in three blank lines and one ending in none produce identical
    bytes. `_echo` reproduces that, and a run with NO output at all still emits
    one newline.
  * NOTHING IS PRINTED UNTIL GO HAS FINISHED. A 300-second test run is silent
    for 300 seconds, on both sides. Streaming would be friendlier and would also
    be a divergence, so it is not done.

-----------------------------------------------------------------------------
THE FAILURE PATH PRINTS TO STDOUT, DELIBERATELY
-----------------------------------------------------------------------------
Both the `|| { echo "$out"; exit 1; }` arm and the `::error::` guard write to
STDOUT, not stderr. That is the twin's behaviour, it is what the GitHub Actions
annotation form needs (`::error::` is only honoured on stdout), and it is
reproduced rather than "improved": a caller that redirects stdout to a file and
watches stderr would otherwise see the failure in a different place depending on
which implementation ran.

-----------------------------------------------------------------------------
THE ONE PLACE A SHELL DIAGNOSTIC HAD TO BE REPRODUCED BY HAND
-----------------------------------------------------------------------------
The twin never probes for `go`. When it is absent, BASH writes
`<$0>: line <n>: go: command not found` and, because the redirection `2>&1` is
applied before the command lookup fails, that message lands INSIDE the captured
output and is echoed to stdout with exit 1. Verified directly, not assumed. The
port has no shell to produce that line, so `_shell_diagnostic` composes it from
`sys.argv[0]` (bash's `$0`) and the caller's own line number (bash's `line n`).
The text after the prefix is byte-identical; the prefix names a different file
because it IS a different file, and the differential masks exactly that prefix
and nothing else.

`cd` is the same shape: a missing `private/renet` makes bash print
`<$0>: line <n>: cd: <dir>: No such file or directory` under `set -e` and exit
1. `os.strerror` supplies the same tail for the same errno, which is where bash
gets it too.

-----------------------------------------------------------------------------
CONSOLE ROOT COMES FROM THIS FILE'S OWN LOCATION
-----------------------------------------------------------------------------
`parents[3]`, matching the twin's `get_repo_root` (`common.sh:205-210`), which
derives the root from `common.sh`'s own `BASH_SOURCE` and never from cwd.
`rediacc_ci.paths.repo_root()` is deliberately not used, on the `build_renet.py`
precedent: it honours `$REDIACC_CI_ROOT` and the twin honours nothing, so a
differential pointing one at a fixture and not the other would diverge for a
reason that has nothing to do with the port.

NO ENVIRONMENT VARIABLE IS READ BY THIS MODULE. The twin's header says "No env
vars" and it means it; the only reads are inside `rediacc_ci.log`, which asks
`NO_COLOR` and `DEBUG` exactly as `common.sh:18` and `common.sh:52` do.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log

# The twin's `ROOT_TESTS` variable, verbatim: a `go test -run` pattern, which is
# an unanchored RE2 alternation matched per test name.
ROOT_TESTS = (
    "TestSaveState_SetsOwnership|TestSaveState_OwnershipMatchesMountDir|TestLoadState_PreservesData"
)

# The twin's `for t in ...` list. It is spelled out a SECOND time in the twin
# rather than derived from ROOT_TESTS by splitting on `|`, and the duplication is
# kept here: the two lists answering to one name is precisely what would let a
# future edit add a test to the `-run` pattern while leaving the guard blind to
# it, and a port that quietly fixed that would no longer be the same gate.
GUARDED_TESTS = (
    "TestSaveState_SetsOwnership",
    "TestSaveState_OwnershipMatchesMountDir",
    "TestLoadState_PreservesData",
)


def console_root() -> pathlib.Path:
    """The repository root, derived the way the twin derives it: from the
    subject file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/private/renet_root_tests.py
    return pathlib.Path(__file__).resolve().parents[3]


def _shell_diagnostic(message: str) -> str:
    """`<$0>: line <n>: <message>`, the shape bash puts on a script's stderr.

    The line number is the CALLER's, taken from the live frame rather than
    hard-coded, so it cannot go stale when this file is reflowed.
    """
    frame = inspect.currentframe()
    back = frame.f_back if frame is not None else None
    lineno = back.f_lineno if back is not None else 0
    return "%s: line %d: %s" % (sys.argv[0], lineno, message)


def _echo(payload: bytes) -> None:
    """`echo "$out"`: all trailing newlines stripped, exactly one added back."""
    sys.stdout.flush()
    sys.stdout.buffer.write(payload.rstrip(b"\n") + b"\n")
    sys.stdout.buffer.flush()


def main(argv: list[str]) -> int:
    """The twin ignores its arguments entirely; so does this, and `argv` is
    accepted only so the signature matches every other module in the package."""
    del argv

    renet_dir = console_root() / "private" / "renet"
    try:
        os.chdir(renet_dir)
    except OSError as exc:
        # `set -e` on a failed `cd`: bash's own diagnostic, then status 1.
        print(
            _shell_diagnostic("cd: %s: %s" % (renet_dir, exc.strerror)),
            file=sys.stderr,
            flush=True,
        )
        return 1

    log.step("Running root-tagged repository tests...")

    command = [
        "go",
        "test",
        "-tags",
        "root",
        "-run",
        ROOT_TESTS,
        "./pkg/repository/",
        "-v",
        "-count=1",
        "-timeout",
        "300s",
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError:
        # Bash writes this INTO the capture, because `2>&1` is applied before the
        # lookup fails. So does this: the message is the captured output.
        _echo(_shell_diagnostic("go: command not found").encode("utf-8", "surrogateescape"))
        return 1
    except PermissionError:
        # MEASURED, NOT ASSUMED: for a `go` that is ON PATH but not executable,
        # bash names the RESOLVED PATH, not the bare word it named for a `go`
        # that was absent. `shutil.which(..., mode=os.F_OK)` repeats bash's
        # search (exists, not a directory) where plain `which` would answer None
        # for exactly the file that caused this branch.
        found = shutil.which("go", mode=os.F_OK) or "go"
        _echo(_shell_diagnostic("%s: Permission denied" % found).encode("utf-8", "surrogateescape"))
        return 1

    out = completed.stdout or b""
    _echo(out)
    if completed.returncode != 0:
        return 1

    # The loud guard. First miss wins, and it names the test rather than the
    # count, so the annotation says which one to go and look at.
    for name in GUARDED_TESTS:
        if b"--- PASS: " + name.encode("utf-8") not in out:
            print(
                "::error::%s did not PASS (root-tagged repository test)" % name,
                flush=True,
            )
            return 1

    log.info("Root-tagged repository tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
