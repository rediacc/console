r"""`drill_summary`'s verdict logic, driven rather than read.

Ported from `.ci/scripts/quality/check-drill-verdicts.sh`, retired in W7 P5;
see `rediacc_ci.quality.__init__` for the phase-5 decision that retired the twin.

WHY THIS EXISTS, in the twin's own words, because the incident is the whole gate:

    Behavioural gate for `drill_summary`'s verdict logic (scripts/drills/lib.sh).

    WHY THIS EXISTS. On 2026-08-05 a drill that ran ZERO assertions -- because
    its environment dependency was absent and declared -- printed:

        0 assertions: 0 passed, 0 failed
        drill transfer PASSED

    Exit code 0, the word PASSED, and nothing whatsoever proven. A dashboard, a
    grep for PASSED, or a reader who did not scroll up to the declaration cannot
    tell that from a real pass. That is the vacuous-green shape the drills exist
    to catch, reproduced by the drills' own reporting.

    The fix makes a zero-assertion run print SKIPPED while keeping exit 0 (a
    DECLARED skip is legitimate; it is the word that was wrong). This gate is
    what stops it regressing, because nothing else can see it: every existing
    check reads exit codes, and the exit code was already correct. The bug lived
    entirely in what the run CLAIMED.

    CONTROL-FIRST. Four verdicts, and the gate fails itself if the harness cannot
    be driven at all:
      1. 0 assertions          -> SKIPPED, and the word PASSED must NOT appear
      2. all assertions pass   -> PASSED   (the CONTROL: without it, a summary
                                  hard-wired to SKIPPED would satisfy 1)
      3. an assertion fails    -> FAILED + non-zero exit
      4. --selftest with no failure -> refuses, because a planted failure that
                                  goes unnoticed means the accounting is broken

THE SUBSHELL RUNS WITH `set +eu` AND THE REASON IS CARRIED: "these libraries are not written to be sourced under strict flags, and a half-loaded library would leave the function undefined -- which would make every assertion below pass VACUOUSLY, i.e. exactly the defect this gate exists to catch, committed by the gate itself."

THE HARNESS IS ASKED FOR BOTH HALVES: "Returns `<exit-code>|<stdout>` so callers can assert on BOTH. Asserting only on the exit code is what let the original defect through."

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE PROBE'S `== "97"` BRANCH IS UNREACHABLE, IN BOTH IMPLEMENTATIONS, AND THAT
IS A REPORTED TWIN DEFECT. `declare -F drill_summary >/dev/null || exit 97` leaves the subshell BEFORE its `printf`, so the command substitution captures
the EMPTY STRING, not `97|`. `"${probe%%|*}"` on an empty string is the empty
string, which is never equal to `97`, so the "Could not load drill_summary" message can never be printed. The condition that actually catches an undrivable harness is `assert_verdict`'s later `[[ -z "$result" ]]` guard, whose own comment says as much: "A gate whose probe failed must not be able to look like a gate whose probe returned nothing interesting."

The port reproduces the dead branch rather than repairing it, because repairing it would emit two lines the twin never emits and the differential would score that as a mismatch. It is named here and in the final report instead.

THE RUNNER IS BASH, AND IT HAS TO BE. The subject is a bash function in `scripts/drills/lib.sh` that reads eight shell variables and writes a formatted table; there is nothing to reimplement in Python and reimplementing it would mean this gate no longer tested the harness the drills actually use. So the port drives the same subshell through `bash -c` and does the ASSERTIONS in
Python.

THE COLOUR VARIABLES COME FROM common.sh IN BOTH, and the source is CONDITIONAL here for one reason: `drill_summary` interpolates `$RED`, `$GREEN`, `$YELLOW` and `$NC` through `printf %b`, and in the twin those are in scope because the gate itself sourced `common.sh` before defining `run_summary`. A `bash -c` child starts with none of them, and under `set +u` they would expand to
empty, which is what a non-tty run produces anyway. Sourcing `common.sh` when it is present makes the two byte-identical on a terminal as well; making it conditional lets the selftest point the gate at a fixture root that has no `.ci` tree at all.

`tr '\n' ' ' <<<"$out" | tail -c 200` IS A BYTE TAIL, and the herestring's own trailing newline becomes a trailing SPACE before the cut. Both details are reproduced: without the added space the 200-byte window lands one byte earlier and the two implementations print different text for the same failure.
"""

import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant

# The harness under test, repo-relative. The twin `cd`s to the root and names it bare; this is the same fact with the cd removed.
DRILL_LIB = "scripts/drills/lib.sh"

# The logger the drill library expects to be in scope, sourced when present.
COMMON_LIB = ".ci/scripts/lib/common.sh"

# The exit code the subshell uses to say "the function is not there". Kept as a named constant even though the branch that reads it is unreachable; see the port notes, and deleting the name would delete the evidence.
UNDRIVABLE = "97"

# How many bytes of the captured summary a failure message shows.
TAIL_BYTES = 200

# The subshell, transliterated line for line from check-drill-verdicts.sh:62-79. `set +eu` is inside and `pipefail` is left alone, exactly as the twin has it.
RUNNER = """
set -euo pipefail
if [ -f "$_DV_COMMON" ]; then
    # shellcheck disable=SC1090
    source "$_DV_COMMON"
fi
(
    set +eu
    # shellcheck disable=SC1090
    source "$_DV_LIB" >/dev/null 2>&1
    declare -F drill_summary >/dev/null || exit 97
    DRILL_NAME="gatecheck"
    DRILL_STARTED_AT=$(date +%s)
    DRILL_COUNT="$_DV_COUNT"
    DRILL_FAILURES="$_DV_FAILURES"
    DRILL_SELFTEST="$_DV_SELFTEST"
    DRILL_ROWS=()
    out="$(drill_summary 2>&1)"
    rc=$?
    printf '%s|%s' "$rc" "$out"
)
"""


def run_summary(root: pathlib.Path, count: str, failures: str, selftest: str = "0") -> str:
    """Drive `drill_summary` with the counters set directly. Returns `rc|stdout`.

    The EMPTY STRING is a real answer and means the subshell died before its printf, which is the only way a caller learns the harness could not be driven. See the port notes for why the `97` it exits with never reaches anybody.
    """
    env = dict(os.environ)
    env.update(
        {
            "_DV_LIB": DRILL_LIB,
            "_DV_COMMON": COMMON_LIB,
            "_DV_COUNT": count,
            "_DV_FAILURES": failures,
            "_DV_SELFTEST": selftest,
        }
    )
    proc = subprocess.run(
        ["bash", "-c", RUNNER],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.stdout.decode("utf-8", "replace")


def tail_summary(out: str) -> str:
    """`tr '\\n' ' ' <<<"$out" | tail -c 200`, both details included.

    The herestring appends a newline that `tr` turns into a trailing SPACE, so the 200-byte window is taken from a string one byte longer than `$out`. A port that dropped that space would print a different first character for every long failure.
    """
    flattened = (out + "\n").replace("\n", " ")
    raw = flattened.encode("utf-8", "surrogateescape")
    return raw[-TAIL_BYTES:].decode("utf-8", "surrogateescape")


class Case:
    """One row of the verdict table, named so the four reads like a spec.

    `forbid` is the half that catches the 2026-08-05 defect: the summary of a run that asserted nothing must not contain the word a dashboard greps for.
    """

    def __init__(
        self,
        label: str,
        count: str,
        fails: str,
        selftest: str,
        want_rc: str,
        want: str,
        forbid: str,
    ) -> None:
        self.label = label
        self.count = count
        self.fails = fails
        self.selftest = selftest
        self.want_rc = want_rc
        self.want = want
        self.forbid = forbid


# The four cases, in the twin's order, with its labels byte for byte.
CASES: tuple[Case, ...] = (
    # 1. THE DEFECT: nothing asserted must not claim a pass (exit 0 is correct).
    Case("0 assertions reads as SKIPPED, never PASSED", "0", "0", "0", "0", "SKIPPED", "PASSED"),
    # 2. THE CONTROL: a real pass must still say PASSED, or assertion 1 is meaningless. Without it a summary hard-wired to SKIPPED would satisfy 1.
    Case("a passing run still reads as PASSED (control fired)", "3", "0", "0", "0", "PASSED", ""),
    # 3. A failure must be loud and non-zero.
    Case("a failing run reads as FAILED and exits non-zero", "3", "1", "0", "1", "FAILED", ""),
    # 4. A selftest whose planted failure did not fire must refuse.
    Case(
        "selftest with no failure refuses (accounting broken)",
        "3",
        "0",
        "1",
        "1",
        "SELFTEST DID NOT FIRE",
        "",
    ),
)


def assert_verdict(root: pathlib.Path, case: Case) -> bool:
    """Drive one case and report. True when it held.

    THE EMPTY-CAPTURE BRANCH COMES FIRST, and the twin's reason is carried: "An empty capture means the subshell died before its printf, i.e. the harness could not be driven at all. Say that, rather than letting it fall through to the rc comparison below and surface as the cryptic 'expected exit 0, got '. A gate whose probe failed must not be able to look like a gate whose probe
    returned nothing interesting."
    """
    result = run_summary(root, case.count, case.fails, case.selftest)
    if result == "":
        log.error(
            "%s: run_summary produced no output \u2014 drill_summary could not be driven."
            % case.label
        )
        return False

    # `${result%%|*}` and `${result#*|}`: the FIRST pipe splits them, so a
    # summary containing a pipe stays intact on the right-hand side.
    head, _, out = result.partition("|")
    rc = head

    if rc != case.want_rc:
        log.error("%s: expected exit %s, got %s" % (case.label, case.want_rc, rc))
        return False
    if case.want not in out:
        log.error("%s: verdict '%s' missing from the summary." % (case.label, case.want))
        log.error("  got: %s" % tail_summary(out))
        return False
    if case.forbid != "" and case.forbid in out:
        log.error("%s: the summary says '%s', which a dashboard or a" % (case.label, case.forbid))
        log.error("  grep will read as proof. A run that asserted nothing must not")
        log.error("  claim it passed \u2014 that is the 2026-08-05 defect.")
        return False
    log.info(case.label)
    return True


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 on an absent harness or any failed case.

    `--selftest` is intercepted BEFORE any real scan. The twin documents itself as taking no arguments ("Usage: check-drill-verdicts.sh") and ignores any it is given.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()

    log.step("Checking drill verdict logic in %s..." % DRILL_LIB)

    if not (root / DRILL_LIB).is_file():
        # A HARNESS THAT VANISHED IS A FAILURE, NOT AN ABSTENTION. Two lines, because the twin prints two and the sentence runs across them.
        log.error("%s not found \u2014 this gate has nothing to check, which is a" % DRILL_LIB)
        log.error("failure, not a pass: a harness that vanished cannot be verified.")
        return 1

    # Prove the harness is reachable before trusting a single verdict.
    #
    # THIS BRANCH CANNOT FIRE. The subshell exits 97 without printing, so the capture is EMPTY and its head is the empty string, never "97". Carried
    # from the twin unchanged and reported as a defect rather than repaired;
    # `assert_verdict`'s empty-result guard is what actually catches an undrivable harness. See the port notes.
    probe = run_summary(root, "1", "0")
    if probe.partition("|")[0] == UNDRIVABLE:
        log.error("Could not load drill_summary from %s." % DRILL_LIB)
        log.error("Refusing to report on a harness this gate cannot actually drive.")
        return 1

    failures = 0
    for case in CASES:
        if not assert_verdict(root, case):
            failures += 1

    if failures > 0:
        log.error("%d drill-verdict check(s) failed" % failures)
        return 1

    log.info(
        "Drill verdicts behave correctly (skipped, passed, failed, and selftest controls all fired)"
    )
    return 0


# A minimal harness that satisfies all four cases. Small enough to read, and shaped like the real `drill_summary`: it branches on DRILL_SELFTEST first, then on DRILL_FAILURES, then on DRILL_COUNT, and returns the same codes.
_GOOD_LIB = """#!/bin/bash
drill_summary() {
    printf '  %d assertions: %d passed, %d failed\\n' \\
        "$DRILL_COUNT" "$((DRILL_COUNT - DRILL_FAILURES))" "$DRILL_FAILURES"
    if [[ "$DRILL_SELFTEST" == "1" ]]; then
        if [[ "$DRILL_FAILURES" -eq 0 ]]; then
            printf '  SELFTEST DID NOT FIRE: a planted failure went unnoticed\\n'
            return 1
        fi
        printf '  selftest fired as designed\\n'
        return 1
    fi
    if [[ "$DRILL_FAILURES" -gt 0 ]]; then
        printf '  drill %s FAILED\\n' "$DRILL_NAME"
        return 1
    fi
    if [[ "$DRILL_COUNT" -eq 0 ]]; then
        printf '  drill %s SKIPPED (0 assertions ran)\\n' "$DRILL_NAME"
        return 0
    fi
    printf '  drill %s PASSED\\n' "$DRILL_NAME"
    return 0
}
"""

# THE 2026-08-05 DEFECT ITSELF, as a fixture: a zero-assertion run that says PASSED. This is the mutant the gate exists to catch, and a suite without it is a suite that has never seen this gate fire.
_VACUOUS_LIB = plant(
    _GOOD_LIB,
    "        printf '  drill %s SKIPPED (0 assertions ran)\\n' \"$DRILL_NAME\"\n        return 0\n",
    "        printf '  drill %s PASSED\\n' \"$DRILL_NAME\"\n        return 0\n",
)


def selftest() -> int:
    """Plant each way the harness can lie, prove the gate refuses; then unplant.

    BOTH DIRECTIONS FOR EVERY CASE. This gate's four assertions are a decision TABLE, and a table has rows that must fire and rows that must not: case 2 exists precisely because a harness hard-wired to SKIPPED would satisfy
    case 1. Every plant below therefore has the good harness as its mirror.
    """
    ctl = Controls("drill-verdicts", floor=16, verbose=True)

    ctl.check("helper: the byte tail keeps a short summary whole", tail_summary("abc"), "abc ")
    ctl.check(
        "helper: the byte tail is the LAST 200 bytes, newlines flattened",
        tail_summary("x" * 300 + "\ny"),
        "x" * 197 + " y ",
    )
    ctl.check("helper: an empty summary flattens to one space", tail_summary(""), " ")

    ctl.check("helper: the four cases are the twin's four", len(CASES), 4)
    ctl.check("helper: case 1 forbids the word a dashboard greps for", CASES[0].forbid, "PASSED")
    ctl.check(
        "helper: case 2 is the CONTROL and forbids nothing, or case 1 is vacuous",
        (CASES[1].want, CASES[1].forbid),
        ("PASSED", ""),
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "scripts" / "drills").mkdir(parents=True)
        lib = root / DRILL_LIB

        def run(body: str | None) -> int:
            if body is None:
                if lib.exists():
                    lib.unlink()
            else:
                lib.write_text(body, encoding="utf-8")
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        ctl.check("CONTROL: a correct harness passes all four cases", run(_GOOD_LIB), 0)

        # THE VACUITY CASE. A harness that has vanished has nothing to verify, and that is a failure rather than an abstention.
        ctl.check("VACUITY: an absent harness is refused", run(None), 1)

        # PLANT 1: the founding defect. 0 assertions printing PASSED.
        ctl.check("PLANT: a zero-assertion run that says PASSED is caught", run(_VACUOUS_LIB), 1)

        # PLANT 2: a harness with no drill_summary at all. The subshell dies before its printf, so the capture is empty; this is the branch that actually catches an undrivable harness, the `97` probe having been unreachable since it was written.
        ctl.check(
            "PLANT: a harness with no drill_summary is refused",
            run("#!/bin/bash\necho nothing here\n"),
            1,
        )
        ctl.check(
            "PLANT: and the capture really is EMPTY, not '97|'",
            run_summary(root, "1", "0"),
            "",
        )

        # PLANT 3: a summary hard-wired to SKIPPED. Case 1 alone would pass; it is case 2, the control, that catches this.
        ctl.check(
            "PLANT: a summary hard-wired to SKIPPED is caught by the CONTROL case",
            run(
                plant(
                    _GOOD_LIB,
                    "    printf '  drill %s PASSED\\n' \"$DRILL_NAME\"\n    return 0",
                    "    printf '  drill %s SKIPPED\\n' \"$DRILL_NAME\"\n    return 0",
                )
            ),
            1,
        )

        # PLANT 4: a failing run that exits 0. The exit code was the ONLY thing the pre-existing checks read, so this is the half they could see.
        ctl.check(
            "PLANT: a failing run that exits 0 is caught",
            run(
                plant(
                    _GOOD_LIB,
                    "        printf '  drill %s FAILED\\n' \"$DRILL_NAME\"\n        return 1",
                    "        printf '  drill %s FAILED\\n' \"$DRILL_NAME\"\n        return 0",
                )
            ),
            1,
        )

        # PLANT 5: a selftest whose planted failure went unnoticed and which says so with the wrong words.
        ctl.check(
            "PLANT: a selftest that does not refuse is caught",
            run(
                plant(
                    _GOOD_LIB,
                    "            printf '  SELFTEST DID NOT FIRE: a planted failure "
                    "went unnoticed\\n'\n            return 1",
                    "            printf '  all good\\n'\n            return 0",
                )
            ),
            1,
        )

        # MIRROR: back to the good harness. Without this, every plant above could be firing because the fixture root was broken rather than because the plant landed.
        ctl.check("MIRROR: the good harness still passes after every plant", run(_GOOD_LIB), 0)

        # The driver itself, both directions, on the good harness.
        ctl.check(
            "DRIVER: 0 assertions returns rc 0 and the word SKIPPED",
            run_summary(root, "0", "0").startswith("0|"),
            True,
        )
        ctl.check(
            "DRIVER: a failing run returns rc 1",
            run_summary(root, "3", "1").startswith("1|"),
            True,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
