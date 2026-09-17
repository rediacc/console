#!/usr/bin/env python3
"""Port of `.ci/scripts/private/renet-integration.sh`.

A thin wrapper: find `private/renet/scripts/ci-test.sh`, hand it an optional `--no-cleanup`, and report where the JUnit XML landed. It reimplements nothing that the submodule's own suite does.

THE BASH TWIN REMAINS THE LIVE CALL SITE. `.github/workflows/ct-tests.yml:1762` spells `run: sudo .ci/scripts/private/renet-integration.sh --no-cleanup`, and nothing else in the tree invokes either subject. THIS MODULE CARRIES NO `---- gate ----` HEADER, and neither does the twin: this is a workflow step, not a registered gate, so `scripts/gate-bind.ts` has nothing to bind here.
Cutover is a separate, later, driver-only step.

-----------------------------------------------------------------------------
THE SUBMODULE GUARD HAS TWO ARMS, AND THE MISSING THIRD ONE IS A REAL DEFECT
-----------------------------------------------------------------------------
The twin does NOT use `common.sh`'s `require_submodule` (common.sh:488-502) even though it sources the same library. It hand-rolls:

    if [[ ! -f "$RENET_DIR/scripts/ci-test.sh" ]]; then
        log_warn "Renet submodule not available, skipping"
        exit 0
    fi

So on a checkout without `private/renet`, the CI step "Run integration tests"
prints one warning and EXITS 0. Driven 2026-09-14 with `CI=true` set and the
marker removed: still one warning, still exit 0. `require_submodule` exists precisely because that reads as green while nothing ran, and both `run-renet.sh` and `run-account.sh` carry the CI arm this one is missing.

IT IS REPRODUCED, NOT FIXED. A port whose verdict differed from its twin's would not be a port, and closing the hole is a cutover-box decision about the twin. The differential (`.ci/rediacc_ci/tests/test_private_renet_integration.py::test_the_missing_ci_arm_is_a_real_hole`)
pins BOTH sides at exit 0 under `CI=true`, so the day someone fixes the twin the
test goes red and names this paragraph.

THE MARKER TEST IS `-f`, NOT `-e`, and that is the opposite of `run-renet.sh`. A DIRECTORY named `ci-test.sh` therefore takes the skip arm here rather than reaching exec and failing with `Is a directory`. Driven both ways; the differential covers it.

-----------------------------------------------------------------------------
ARGUMENT PARSING: ONE FLAG, EVERYTHING ELSE SILENTLY DROPPED
-----------------------------------------------------------------------------
The twin's loop is `case "$1" in --no-cleanup) ...;; *) shift;; esac`, so `renet-integration.sh --nocleanup` (one hyphen short) is accepted, ignored, and runs WITH cleanup. There is no unknown-argument arm. Reproduced deliberately and named here rather than improved, because a port that started refusing arguments the twin accepts would change what the CI step does.

The flag is passed on UNQUOTED in the twin (`"$CI_TEST" $NO_CLEANUP`), which is what makes the empty case expand to ZERO words rather than one empty word. That is the only reason the default invocation is `ci-test.sh` with no arguments at all, and it is why `_command` appends conditionally instead of always.

-----------------------------------------------------------------------------
NO `cd` HAPPENS, IN EITHER IMPLEMENTATION
-----------------------------------------------------------------------------
`ci-test.sh` is invoked by absolute path from whatever directory the caller was in, and it locates itself. The differential drives both subjects from a neutral directory and records the child's cwd, because that absence is only observable
from the child.

-----------------------------------------------------------------------------
NO ENVIRONMENT VARIABLE IS READ BY THIS MODULE
-----------------------------------------------------------------------------
Not even `CI`: the guard above has no CI arm to read it with. The only reads in the whole run are inside `rediacc_ci.log`, which asks `NO_COLOR` and `DEBUG` exactly as `common.sh:18` and `common.sh:52` do.

CONSOLE ROOT comes from this file's own location (`parents[3]`), matching the twin's `get_repo_root` (common.sh:205-210). `rediacc_ci.paths.repo_root()` is deliberately not used, on the `run_renet.py` precedent: it honours `$REDIACC_CI_ROOT` and the twin honours nothing, so a differential pointing one at a fixture and not the other would diverge for a reason that has nothing to do
with the port.
"""

from __future__ import annotations

import inspect
import pathlib
import subprocess
import sys

from rediacc_ci import log

# The one flag the twin recognises, and the exact string it forwards. They are
# the same string in the twin (`NO_CLEANUP="--no-cleanup"`), which is why one
# constant serves both roles here.
NO_CLEANUP_FLAG = "--no-cleanup"


def console_root() -> pathlib.Path:
    """The repository root, derived the way the twin derives it: from the subject file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/private/renet_integration.py
    return pathlib.Path(__file__).resolve().parents[3]


def _shell_diagnostic(message: str) -> str:
    """`<$0>: line <n>: <message>`, the shape bash puts on a script's stderr.

    The line number is the CALLER's, taken from the live frame rather than hard-coded, so it cannot go stale when this file is reflowed.
    """
    frame = inspect.currentframe()
    back = frame.f_back if frame is not None else None
    lineno = back.f_lineno if back is not None else 0
    return "%s: line %d: %s" % (sys.argv[0], lineno, message)


def no_cleanup(argv: list[str]) -> str:
    """The twin's whole argument loop, as the value of `$NO_CLEANUP`.

    Returns `"--no-cleanup"` if the flag appears ANYWHERE in argv, else `""`. The twin's loop assigns the same literal however many times it sees the flag and shifts past everything else without complaint, so position, repetition and unknown tokens all make no difference. Returning the STRING rather than a bool keeps the twin's "this variable holds the argument to forward" shape,
    which is what makes the empty case expand to nothing.
    """
    return NO_CLEANUP_FLAG if NO_CLEANUP_FLAG in argv else ""


def command(ci_test: pathlib.Path, flag: str) -> list[str]:
    """`"$RENET_DIR/scripts/ci-test.sh" $NO_CLEANUP`, word-split as bash splits it.

    The UNQUOTED expansion is the whole content of this function: an empty `$NO_CLEANUP` contributes zero words, not one empty word, so the default run passes no arguments at all. A port that always appended would hand `ci-test.sh` an empty argument, and a suite that parsed its own argv would see a difference no stream could show.
    """
    return [str(ci_test), flag] if flag else [str(ci_test)]


def main(argv: list[str]) -> int:
    flag = no_cleanup(argv)

    renet_dir = console_root() / "private" / "renet"
    ci_test = renet_dir / "scripts" / "ci-test.sh"

    # `[[ ! -f ... ]]`: FILE-ness, following symlinks. A directory of that name takes this arm. NO CI ARM, deliberately -- see the module docstring.
    if not ci_test.is_file():
        log.warn("Renet submodule not available, skipping")
        return 0

    log.step("Running renet integration tests...")

    try:
        completed = subprocess.run(command(ci_test, flag), check=False)
    except PermissionError:
        # The `-f` guard already proved this is a regular file, so EACCES here means "not executable" and nothing else; bash prints exactly this and exits 126. Driven against bash before the branch was written.
        print(_shell_diagnostic("%s: Permission denied" % ci_test), file=sys.stderr, flush=True)
        return 126
    except OSError:
        # Reachable only for an exotic exec failure past the `-f` guard: a dangling symlink resolved between the test and the call, or a shebang naming a missing interpreter. THE SECOND ONE DIVERGES AND IT IS SAID HERE RATHER THAN LEFT TO BE DISCOVERED: bash prints `<$0>: <script>: <interp>: bad interpreter: No such file or directory` -- no `line n:`, and status 126 -- while this
        # prints the `line n:` form and 127. Measured 2026-09-14. Emulating it would mean parsing shebangs inside an error path; the arm exists so such a case exits like a shell rather than raising a traceback that reads as flake.
        print(
            _shell_diagnostic("%s: No such file or directory" % ci_test),
            file=sys.stderr,
            flush=True,
        )
        return 127

    # `set -e`: the suite's own status, unchanged, and nothing printed after it. The two log lines below are UNREACHABLE on a failing run, on both sides, so a red integration run never claims "Integration tests completed".
    if completed.returncode != 0:
        return completed.returncode

    results = renet_dir / "test-results.xml"
    if results.is_file():
        log.info("Integration test results available at: %s" % results)

    log.info("Integration tests completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
