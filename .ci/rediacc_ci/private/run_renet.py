#!/usr/bin/env python3
"""Port of `.ci/scripts/private/run-renet.sh`, the registered gate `check:ci-renet`.

A thin wrapper: check that the `private/renet` submodule is checked out, pin
`GOTOOLCHAIN`, and hand one stage name to the submodule's own
`private/renet/.ci/ci.sh`. It reimplements nothing that script does.

THE BASH TWIN REMAINS THE REGISTERED GATE. `package.json:251` spells
`"check:ci-renet": ".ci/scripts/private/run-renet.sh quality"`,
`scripts/ci-runner/manifest.ts:3652` names that same file as the gate's `leaf`,
and `.github/workflows/ct-tests.yml:1718` runs `... run-renet.sh test`. THIS
MODULE CARRIES NO `---- gate ----` HEADER on purpose: the header is what
`scripts/gate-bind.ts` reads, and a second file claiming `id: check:ci-renet`
would give one gate two owners. Cutover is a separate, later, driver-only step.

-----------------------------------------------------------------------------
THE SUBMODULE GUARD IS THE ONLY DECISION IN THE FILE, AND IT HAS THREE ARMS
-----------------------------------------------------------------------------
`common.sh:488-502`, reached here through `rediacc_ci.core.common
.require_submodule` rather than re-derived, because that function is already
differentially checked against the same twin and a second copy would be a second
answer to one question:

  marker present        -> run the stage
  absent, `CI` == true  -> three `log_error` lines and EXIT 1
  absent, otherwise     -> one `log_warn` and EXIT 0

The middle arm is the whole reason the guard is not a bare `[[ -e ]] || exit 0`,
and `common.sh` says why in its own comment: this gate carries govulncheck,
deadcode and golangci-lint, and all three would report success while checking
nothing. The third arm keeps a fresh clone without `--recursive` workable, and
it is a REAL HOLE IN THE LOCAL GATE that is documented rather than closed
(`.ci/scripts/test/gates/test-gate-anti-vacuity.sh:317` records that this script
used to exit 0 silently in CI too). `npm run check:ci-renet` on a machine with
no submodule prints one warning and exits 0.

`CI` is tested as the LITERAL `"${CI:-false}" == "true"`, not through an
is-CI helper, so `GITHUB_ACTIONS=true` with `CI` unset takes the LOCAL arm. That
inconsistency belongs to the twin and is reproduced, not harmonised.

THE MARKER TEST IS `-e`, NOT `-f`. An uninitialised submodule leaves its mount
point behind as an empty directory, so existence is the right question for the
DIRECTORY case; the consequence at the FILE level is that a directory named
`ci.sh` passes the guard and then fails at exec time with `Is a directory` and
status 126. Both sides do that, and the differential pins it.

-----------------------------------------------------------------------------
GOTOOLCHAIN IS EXPORTED, NOT PASSED
-----------------------------------------------------------------------------
`export GOTOOLCHAIN="${GOTOOLCHAIN:-auto}"` is reproduced as a mutation of
`os.environ`, which is what an export IS: the child inherits it and so would any
further child. Writing it into a per-call `env=` dict would look equivalent and
would not be, for a `ci.sh` that spawns its own helpers.

`:-` means UNSET OR EMPTY both become `auto`. `GOTOOLCHAIN=""` therefore does
not disable the pin, it selects `auto`, and the port reads the variable directly
at the call site (`os.environ.get("GOTOOLCHAIN", "")`) rather than through any
`env = dict(os.environ)` alias, so the env-manifest reader can see the name.

WHY `auto` AND NOT A PINNED VERSION: the twin's own comment records that this
used to pin `go1.25.10+auto` while `private/renet/go.mod` declared `go1.25.12`,
already diverged and masked only because the `+auto` suffix silently upgrades.
`go.mod`'s `toolchain` directive is the single source of truth.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO
-----------------------------------------------------------------------------
Exactly one thing: `private/renet/.ci/ci.sh <stage>`, with the parent's cwd,
stdout and stderr, and its exit status returned unchanged. NO `cd` HAPPENS
FIRST, in either implementation, so the stage inherits whatever directory the
caller was in; `ci.sh` locates itself. The differential
(`.ci/rediacc_ci/tests/test_private_run_renet.py`) puts a recording `ci.sh` in
the fixture and compares its argv, cwd and inherited `GOTOOLCHAIN`, because a
port that printed the same banner while never invoking the stage would satisfy
a stdout-only comparison and run no Go tests at all.

EXTRA ARGUMENTS ARE DROPPED IN SILENCE. `run-renet.sh quality test` runs
`quality` and says nothing about `test`; so does this. Reproduced deliberately,
not endorsed.

CONSOLE ROOT comes from this file's own location (`parents[3]`), matching the
twin's `get_repo_root`; `rediacc_ci.paths.repo_root()` is not used because it
honours `$REDIACC_CI_ROOT` and the twin honours nothing.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `STAGE="${1:-all}"`. The twin documents four (all, quality, test, build) and
# validates none of them: an unknown stage is forwarded to `ci.sh`, which is
# where the twin leaves the decision, so no validation is invented here either.
DEFAULT_STAGE = "all"

# The label `require_submodule` puts in front of both its CI error and its local
# warning. Verbatim from the twin, because a caller greps the warning.
SUBMODULE_LABEL = "Renet submodule"


def console_root() -> pathlib.Path:
    """The repository root, derived the way the twin derives it: from the
    subject file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/private/run_renet.py
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


def stage_of(argv: list[str]) -> str:
    """`"${1:-all}"`: unset OR EMPTY yields `all`, and `$2` onward is ignored."""
    return argv[0] if argv and argv[0] else DEFAULT_STAGE


def main(argv: list[str]) -> int:
    stage = stage_of(argv)
    renet_dir = console_root() / "private" / "renet"
    ci_sh = renet_dir / ".ci" / "ci.sh"

    try:
        present = common.require_submodule(ci_sh, SUBMODULE_LABEL)
    except common.RefusalError as exc:
        # The CI arm: three lines through `log_error`, then the twin's status 1.
        exc.report()
        return exc.code
    if not present:
        # `require_submodule ... || exit 0`. The warning was already printed.
        return 0

    log.step("Running renet CI (stage: %s)..." % stage)

    # An EXPORT, not a per-call env: `ci.sh` spawns its own children.
    os.environ["GOTOOLCHAIN"] = os.environ.get("GOTOOLCHAIN", "") or "auto"

    try:
        completed = subprocess.run([str(ci_sh), stage], check=False)
    except PermissionError:
        # MEASURED, NOT ASSUMED. `execve` on a DIRECTORY returns EACCES, so
        # Python raises PermissionError for both the unreadable file and the
        # directory; bash stats the target and says `Is a directory` for the
        # second. Driven both ways against bash before this branch was written.
        # The status is 126 either way.
        why = "Is a directory" if ci_sh.is_dir() else "Permission denied"
        print(_shell_diagnostic("%s: %s" % (ci_sh, why)), file=sys.stderr, flush=True)
        return 126
    except OSError:
        # bash's "command not found" status for a path it cannot execute. The
        # guard above already proved the path EXISTS, so this arm is reachable
        # only for an exotic failure (a dangling symlink, a bad interpreter
        # line); it is here so such a case exits like the twin rather than
        # raising a traceback that reads as flake.
        print(
            _shell_diagnostic("%s: No such file or directory" % ci_sh), file=sys.stderr, flush=True
        )
        return 127

    # `set -e`: the stage's own status, unchanged, and nothing added on success.
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
