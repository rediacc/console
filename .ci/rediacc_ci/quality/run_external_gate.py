"""Port of `.ci/scripts/quality/run-external-gate.sh`.

The wrapper that decides whether a gate depending on the OUTSIDE WORLD is allowed to redden today's run. The twin's header carries the measurement that justifies it: 5 of the 8 nightlies before 2026-08-04 failed on nothing but external drift -- a new rclone release, freshly published npm advisories, a new action version. The world moved, not this tree, and the `no-external-quality`
label cannot help on a `schedule` event where no PR label can ever apply.

THE THREE-STATE FLAG, computed by ci.yml's initialize job as `external_quality`, and only TWO of its states ever reach this file:

  hard  pull request without the label. The gate runs and its exit code is
        kept, unchanged, including 126/127/128+N.
  skip  pull request WITH the label. The step does not run at all -- this is
        expressed in the step's `if:`, so this wrapper never sees the string
        and deliberately does not accept it. `announce-gate-skips.sh` is what
        makes that skip visible; the two scripts are complements.
  soft  schedule / workflow_dispatch. The gate RUNS and REPORTS, but a failure
        becomes a `::warning::` plus a step summary and exit 0, so external
        drift shows yellow instead of reddening the only suite that validates
        main.

UNSET IS HARD, AND AN UNKNOWN VALUE IS A REFUSAL (exit 2). Both are the same argument: guessing `soft` would quietly disable a blocking gate, and a wiring
break must never do that silently. `EXTERNAL_QUALITY_MODE=skip` therefore hits
the refusal too, which looks surprising until you notice that a `skip` reaching this wrapper means the step's `if:` did not fire and the workflow IS miswired.

WHY A WRAPPER AND NOT `continue-on-error`: `check-workflows.sh` bans that key repo-wide, and the repo's precedent for non-blocking behaviour is a script-level soft-fail (`scripts/gates/check-embed-asset-freshness.ts`, "FAIL SOFT"). This is that precedent factored out once instead of re-implemented inside every external gate.

NOT A REGISTERED GATE ITSELF; it is a transparent PREFIX on four registered ones. `grep -n run-external-gate package.json` matches nothing, and `scripts/gates/check-ci-parity.ts:262-268` special-cases it precisely so a gate wrapped in it still counts as CI-covered -- the leaf is the wrapped `npm run check:...`, not the wrapper. Live call sites: `ci-quality.yml:1084`
(check:actions), `:1289` (check:ci-external-links), `:1299` (check:ci-dkim-notify), `:2083` (check:ci-go-deps), `:2150` (check:ci-embed-asset-freshness), `:2163` (check:ci-devcontainer-pins). Its own coverage is the bash gate test `.ci/scripts/test/gates/test-external-gate-wrapper.sh`, which still drives the twin.

THE CHILD IS EXECUTED, NOT SHELLED. `"$@"` runs the argument vector directly, so `run-external-gate.sh 'a b'` looks for a program literally named `a b` rather than running `a` with an argument. `subprocess.run(argv)` without
`shell=True` is the same thing, and using `shell=True` here would be a
behavioural change disguised as a convenience.

STDOUT AND STDERR ARE INHERITED, never captured. The wrapped gate's output IS the step's output; buffering it to re-emit later would reorder it against this wrapper's own `::warning::` and would hide a gate that hangs after printing.

EXIT-CODE TRANSLATION IS THE ONE PLACE THIS PORT HAS TO DO WORK BASH GETS FREE.
`subprocess` reports a signalled child as a NEGATIVE returncode; the shell reports `128 + N`. A port that passed the negative number through would exit 0
for SIGKILL (`-9 & 0xff`... after Python's own exit-code masking) or otherwise
lie about a killed gate, which in `hard` mode is the difference between a red and a green. `_shell_status` does the conversion, and the differential drives a real SIGTERM through both sides. The two spawn failures are translated the same way, to bash's own codes: 127 not-found, 126 found-but-not-executable.

THREE DIVERGENCES, ALL IN MESSAGE TEXT AND NONE IN AN EXIT CODE, driven 2026-09-10 against the twin:

  1. `$0` in the usage line. A module invoked as `python3 -m ...` cannot have
     the shell's `$0`, and hardcoding the twin's `.sh` path would print a path
     that did not run. The differential masks the program token.
  2. Spawn failures. bash prints `<script>: line 49: <cmd>: command not found`;
     this prints `run-external-gate: <cmd>: command not found`. Both exit 127.
  3. A SIGNALLED CHILD. bash's job-control notice
     `Terminated                 "$@"` lands on the twin's stderr and has no
     Python equivalent. The exit code is 143 on both sides, which is the part
     that decides red versus green, and the differential asserts it directly.

K=5 LEDGER: `.ci/shadow/w7p6-run-external-gate.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

MODES = ("hard", "soft")


def _shell_status(returncode: int) -> int:
    """A `subprocess` returncode as the shell would report it.

    Negative means "killed by signal N", which every POSIX shell reports as `128 + N`. Nothing else moves.
    """
    return 128 + (-returncode) if returncode < 0 else returncode


def main(argv: list[str]) -> int:
    # `${EXTERNAL_QUALITY_MODE:-hard}`: EMPTY falls back to hard as well, which
    # is the fail-closed direction and the twin's.
    mode = os.environ.get("EXTERNAL_QUALITY_MODE") or "hard"

    if not argv:
        print(
            "usage: EXTERNAL_QUALITY_MODE=hard|soft %s <command...>" % sys.argv[0],
            file=sys.stderr,
        )
        return 2

    if mode not in MODES:
        print(
            "run-external-gate: unknown EXTERNAL_QUALITY_MODE '%s' (expected hard|soft)" % mode,
            file=sys.stderr,
        )
        return 2

    joined = " ".join(argv)

    try:
        completed = subprocess.run(argv, check=False)
        rc = _shell_status(completed.returncode)
    except FileNotFoundError:
        # bash: `<script>: line 49: <cmd>: command not found`, status 127.
        print("run-external-gate: %s: command not found" % argv[0], file=sys.stderr)
        rc = 127
    except PermissionError:
        # bash: `<script>: line 49: <cmd>: Permission denied`, status 126.
        print("run-external-gate: %s: Permission denied" % argv[0], file=sys.stderr)
        rc = 126

    if rc == 0:
        return 0

    if mode == "soft":
        print(
            "::warning::external gate '%s' failed (exit %d) in soft mode: external drift "
            "reported, run stays green (blocking on pull requests)" % (joined, rc)
        )
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write("### External gate soft-failed: `%s` (exit %d)\n" % (joined, rc))
                fh.write("\n")
                fh.write("Scheduled runs report external drift (new upstream releases,\n")
                fh.write("new advisories) as a warning instead of a red; the identical\n")
                fh.write(
                    "failure blocks on a pull request. See docs/agent-reference/ci-gates.md.\n"
                )
        return 0

    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
