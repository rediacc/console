"""The mutation runner itself must keep working.

Ported from `.ci/scripts/quality/check-mutate-check.sh`, which W7 P5 batch A2 retired once `.ci/shadow/w7p2-mutate-check.observations.jsonl` asserted equivalence over five distinct trees. Its gate header registers it as step "Mutation runner self-test", needs none, selftest true.

WHAT THIS DOES AND DOES NOT PROTECT, carried whole from the twin because the distinction is the entire reason the gate is small:

    It does NOT force anyone to run a mutation for every new test case; that is
    not gateable (see the rebuttal in agent/plans/PLAN-promote-mutation-runner.md,
    section "Gate or tool?"). What it protects is the INSTRUMENT: mutate-check.sh
    must keep producing the right verdict for each of its four outcomes, so it
    cannot silently rot into something that always says OK. An instrument nobody
    is forced to use is still worth having; an instrument that lies is worse than
    none.

    Every scenario runs against a miniature fixture suite, so the whole gate
    takes seconds rather than the 8-plus minutes two passes of the real suite
    would cost.

    CONTROL-FIRST BY CONSTRUCTION: scenario 1 is the only one that may exit 0. If
    the runner's logic collapsed into "always succeed", scenarios 2, 3 and 4 would
    all fail this gate. If it collapsed into "always fail", scenario 1 would.

THE FOUR VERDICTS, and the twin's reason for each, kept at the scenario that asserts it:

  1. red-then-green. The good case; the ONLY exit 0.
  2. THE VERDICT THIS TOOL EXISTS FOR. Case 901 is red in both directions, so its
     red proves nothing about the defect. Reporting this as success is the precise
     failure that cost a session hours, so it is the load-bearing scenario.
  3. A mutation that applies cleanly but changes nothing observable must be
     reported as an undetected defect, never as a pass.
  4. A `--from` string that is absent is a HARD ERROR. If it were a warning, the
     run would proceed with an unmutated sandbox, the mutant would come back
     green, and that reads exactly like scenario 3: indistinguishable from a real
     finding.
  5. The runner's own first bug: `^FAIL` matches nothing because the suite
     indents, so a failing run printed an empty failure list. The fixture prints
     indented lines exactly like the real suite, so scenario 1 passing at all
     proves the indentation-aware matching still works. Asserted explicitly so
     the reason this fixture indents cannot be lost to a future tidy-up.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE RUNNER IS DRIVEN, NEVER REIMPLEMENTED. This gate's subject is a bash program and its four exit codes; a Python reimplementation of mutate-check.sh would be a second instrument and this gate would then certify the wrong one. Every scenario is a subprocess, and the twin's `2>&1` capture is reproduced by merging the child's two streams into one string -- which is the ONE place in
this package where merging is correct, because the captured text is the gate's INPUT rather than its output.

`ok` AND `FAIL` CARRY RAW ESCAPES, UNCONDITIONALLY, and that is the twin's behaviour rather than an oversight to fix. `printf ' \\033[0;32mok\\033[0m %s\\n'` has no tty test at all, so this gate writes colour into a pipe and into a CI log. `scripts/lib/shadow-gate.ts` strips ANSI before comparing, so the escapes cost nothing there; they are carried because a port that removed them
would print different BYTES to a human diffing the two, and reported as a twin finding.

THE FAILURE LINE IS NOT A FINDING TO THE COMPARATOR, and knowing that is what keeps this port honest. `bad()` prints ` FAIL <label>` with ONE space, while `scripts/lib/shadow-gate.ts`'s marker is `/^FAIL\\s\\s+/` (two or more) or `/^FAIL:/`. So a failing scenario's line is classified as CHATTER, and the only compared finding this gate emits is the final `✗ N mutate-check.sh
self-test(s) failed`. That is why the differential fixtures vary the NUMBER of failing scenarios rather than which one fails: the number is the only thing the ledger can see. Stated here so nobody reads a passing differential as proof that the per-scenario labels agree.

THE DETAIL BLOCK IS `sed 's/^/ /' | head -12`: seven spaces, twelve lines, on STDOUT. Reproduced exactly, including the truncation, because those lines land under a chatter header and any of them shaped like `<file>.<ext>:<line>:` is promoted to a finding by the comparator's path-line rule.

`grep -qE '^\\s+echo " (PASS|FAIL): '` IS SCANNED LINE BY LINE with an explicit POSIX space class. `grep` applies the pattern per line, so `\\s` can never reach a newline there; Python's `\\s` on a str would additionally match U+00A0 and U+2028, so the class is written out rather than abbreviated.

ONE DELIBERATE DIVERGENCE, named rather than hidden: if the runner exists but is NOT EXECUTABLE, bash reports 126 with its own "Permission denied" text captured into the scenario output, while this port raises OSError and reports 126 with an empty output. The twin's own precondition loop tests `-f`, not `-x`, so both implementations reach that state the same way. No fixture in the
ledger exercises it, and it is written down because an undocumented divergence is the kind a later reader takes for a defect in the port.
"""

import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The three files the twin refuses to run without, relative to the repo root.
RUNNER_REL = (".ci", "scripts", "test", "mutate-check.sh")
FIXDIR_REL = (".ci", "scripts", "test", "fixtures", "mutate-check")
SUITE_NAME = "fixture-suite.sh"
TARGET_NAME = "fixture_mod.py"

# `grep -qE '^\s+echo " (PASS|FAIL): '`, with [[:space:]] written out. See the port notes for why `\s` is the wrong abbreviation here.
INDENTED_RESULT_RE = re.compile(r"^[ \t\v\f\r]+echo \"  (PASS|FAIL): ")

# The colour codes the twin printf's unconditionally. No tty test in the twin, so none here; see the port notes.
_GREEN = "\033[0;32m"
_RED = "\033[0;31m"
_NC = "\033[0m"

# How a scenario judges the runner's exit code. Three shapes, because the four scenarios genuinely ask three different questions and collapsing them into "non-zero is bad" is how scenario 4 would stop distinguishing a hard error from an ordinary failure.
RC_ZERO = "eq0"
RC_NONZERO = "ne0"
RC_TWO = "eq2"


def rc_ok(mode: str, rc: int) -> bool:
    """Does `rc` satisfy the scenario's exit-code condition?

    Exported so `--selftest` can drive all three modes in both directions without a subprocess. A KeyError-free `raise` on an unknown mode is deliberate: a typo'd mode that silently answered False would turn a control into a permanent red nobody could explain.
    """
    if mode == RC_ZERO:
        return rc == 0
    if mode == RC_NONZERO:
        return rc != 0
    if mode == RC_TWO:
        return rc == 2
    raise ValueError("unknown rc mode %r" % mode)


def scenario_passed(mode: str, rc: int, out: str, needle: str) -> bool:
    """The twin's `if [[ rc-condition ]] && grep -qF "<needle>" <<<"$OUT"`.

    `grep -qF` is a FIXED-STRING search, not a regex, so the needle is compared
    with `in` rather than compiled. That matters for "does not detect this
    defect", which contains no metacharacter today and would silently become a pattern the day someone added one.
    """
    return rc_ok(mode, rc) and needle in out


def indented_result_lines(text: str) -> bool:
    """Scenario 5: does the fixture suite still print INDENTED result lines?

    The whole reason the fixture indents is that the runner's first bug was a `^FAIL` that matched nothing. A fixture tidied to print flush-left would make scenario 1 pass while the regression it guards went unguarded.
    """
    return any(INDENTED_RESULT_RE.match(line) for line in text.split("\n"))


class _Tally:
    """The twin's `ok` / `bad` pair and its FAILED counter, transliterated.

    Not `rediacc_ci.controls.Controls`: these strings are the gate's OUTPUT CONTRACT and `scripts/lib/shadow-gate.ts` compares them against the bash twin's, so a nicer wording here is a false mismatch there. The same decision, and the same reasoning, as `rediacc_ci.quality.staging_tag_guard._GateTally`.
    """

    def __init__(self) -> None:
        self.failed = 0

    def ok(self, label: str) -> None:
        print("  %sok%s   %s" % (_GREEN, _NC, label))

    def bad(self, label: str, detail: str = "") -> None:
        print("  %sFAIL%s %s" % (_RED, _NC, label))
        if detail:
            # `sed 's/^/ /' <<<"$2" | head -12`. The herestring appends a newline, so sed sees at least one line even for a single word.
            for line in (detail + "\n").splitlines()[:12]:
                print("       %s" % line)
        self.failed += 1


def run_scenario(
    runner: pathlib.Path, args: list[str], env_extra: dict[str, str] | None = None
) -> tuple[int, str]:
    """One `"$RUNNER" ... 2>&1` capture. Returns (exit code, merged output).

    MERGING IS CORRECT HERE and nowhere else in this package: the merged text is what the twin greps, so splitting the streams would change which scenarios pass. `rediacc_ci.tests.differential` never merges, because there the streams are the thing under test.
    """
    environ = dict(os.environ)
    if env_extra:
        environ.update(env_extra)
    try:
        completed = subprocess.run(
            [str(runner), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            env=environ,
            check=False,
        )
    except OSError:
        # See the port notes: bash reports 126 with its own diagnostic text, this reports 126 with none. No ledger fixture reaches here.
        return 126, ""
    # `$(...)` STRIPS EVERY TRAILING NEWLINE, and the twin captures through it. Without this the detail block printed one extra blank line per failing scenario, because `<<<"$OUT"` re-adds exactly one newline and `splitlines` then sees a final empty record. Found 2026-09-06 by the byte-for-byte case in tests/test_quality_mutate_check.py; the shadow differential could NOT see it,
    # because `bad()` prints ` FAIL <label>` with ONE space and scripts/lib/shadow-gate.ts needs two, so the whole block is chatter there.
    return completed.returncode, (completed.stdout or "").rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when all five scenarios hold, 1 otherwise.

    `--selftest` is intercepted BEFORE any real scan, which is the addition the twin does not have. The twin takes no arguments, so no caller passes it.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    runner = root.joinpath(*RUNNER_REL)
    fixdir = root.joinpath(*FIXDIR_REL)
    suite = fixdir / SUITE_NAME
    target = fixdir / TARGET_NAME

    # The twin exits at the FIRST missing file, so the loop order is part of the message a reader gets. Kept.
    for required in (runner, suite, target):
        if not required.is_file():
            print("check-mutate-check: missing %s" % required, file=sys.stderr)
            return 1

    tally = _Tally()
    print("info: exercising mutate-check.sh through all four verdicts")

    common = ["--suite", str(suite), "--file", str(target)]

    # 1. The good case: mutation kills case 900, baseline is clean. The ONLY exit 0.
    rc, out = run_scenario(
        runner,
        [
            *common,
            "--from",
            "GUARD_ENABLED = True",
            "--to",
            "GUARD_ENABLED = False",
            "--expect-red",
            "900",
        ],
    )
    if scenario_passed(RC_ZERO, rc, out, "Both directions hold"):
        tally.ok("red-then-green exits 0")
    else:
        tally.bad("red-then-green did not exit 0 (rc=%d)" % rc, out)

    # 2. Case 901 is red in BOTH directions. Reporting that as success is the failure this whole tool exists for.
    rc, out = run_scenario(
        runner,
        [
            *common,
            "--from",
            "GUARD_ENABLED = True",
            "--to",
            "GUARD_ENABLED = False",
            "--expect-red",
            "901",
        ],
        {"MUTCHK_FIXTURE_ALWAYS_BROKEN": "1"},
    )
    if scenario_passed(RC_NONZERO, rc, out, "PROVED NOTHING"):
        tally.ok("red in BOTH directions is reported as PROVED NOTHING, not success")
    else:
        tally.bad("a case red in both directions was not caught (rc=%d)" % rc, out)

    # 3. A mutation that applies cleanly and changes nothing observable.
    rc, out = run_scenario(
        runner,
        [*common, "--from", '"unmutated"', "--to", '"mutated-but-harmless"', "--expect-red", "900"],
    )
    if scenario_passed(RC_NONZERO, rc, out, "does not detect this defect"):
        tally.ok("a mutation the suite cannot see is reported as undetected")
    else:
        tally.bad("an undetected mutation was not reported (rc=%d)" % rc, out)

    # 4. An absent `--from` is a HARD ERROR, exit 2.
    rc, out = run_scenario(
        runner,
        [
            *common,
            "--from",
            "this string is nowhere in the fixture",
            "--to",
            "x",
            "--expect-red",
            "900",
        ],
    )
    if scenario_passed(RC_TWO, rc, out, "MUTATION DID NOT APPLY"):
        tally.ok("a no-op mutation is a hard error, not a silent green")
    else:
        tally.bad("a no-op mutation was not a hard error (rc=%d)" % rc, out)

    # 5. The fixture must still INDENT, or the `^FAIL` regression is unguarded.
    if indented_result_lines(suite.read_text(encoding="utf-8", errors="replace")):
        tally.ok("the fixture prints INDENTED result lines, as the real suite does")
    else:
        tally.bad("the fixture stopped indenting; the ^ *FAIL regression is unguarded")

    print()
    if tally.failed == 0:
        print(
            "%s✓%s mutate-check.sh produces the right verdict in all four outcomes" % (_GREEN, _NC)
        )
        return 0
    print("%s✗%s %d mutate-check.sh self-test(s) failed" % (_RED, _NC, tally.failed))
    return 1


def selftest() -> int:
    """Plant each violation, prove it fires; remove it, prove it does not.

    THE DECISION FUNCTIONS, NOT THE SUBPROCESSES. Driving the real runner here would re-run the gate and prove only that the gate agrees with itself; what is worth pinning is the three exit-code modes, the fixed-string match, and the indentation rule, each in BOTH directions.
    """
    ctl = Controls("mutate-check", floor=18, verbose=True)

    ctl.check("CONTROL: rc 0 satisfies the zero mode", rc_ok(RC_ZERO, 0), True)
    ctl.check("PLANT: rc 1 does not satisfy the zero mode", rc_ok(RC_ZERO, 1), False)
    ctl.check("CONTROL: rc 1 satisfies the non-zero mode", rc_ok(RC_NONZERO, 1), True)
    ctl.check("PLANT: rc 0 does not satisfy the non-zero mode", rc_ok(RC_NONZERO, 0), False)
    ctl.check("CONTROL: rc 2 satisfies the two mode", rc_ok(RC_TWO, 2), True)
    # THE ONE THAT MATTERS: scenario 4 asks for a HARD error, and any other non-zero code is the runner failing for some other reason. A port that
    # relaxed this to `!= 0` would pass while the distinction was gone.
    ctl.check("PLANT: rc 1 does NOT satisfy the two mode", rc_ok(RC_TWO, 1), False)
    ctl.raises(
        "an unknown rc mode raises rather than answering False", ValueError, rc_ok, "nope", 0
    )

    ctl.check(
        "CONTROL: the right code and the right needle pass",
        scenario_passed(RC_ZERO, 0, "...\nBoth directions hold\n", "Both directions hold"),
        True,
    )
    ctl.check(
        "PLANT: the right code with the WRONG needle fails",
        scenario_passed(RC_ZERO, 0, "everything is fine\n", "Both directions hold"),
        False,
    )
    ctl.check(
        "PLANT: the right needle with the WRONG code fails",
        scenario_passed(RC_ZERO, 1, "Both directions hold\n", "Both directions hold"),
        False,
    )
    ctl.check(
        "MIRROR: the needle is a FIXED string, so a regex metacharacter is literal",
        scenario_passed(RC_NONZERO, 1, "a.c", "a.c")
        and not scenario_passed(RC_NONZERO, 1, "abc", "a.c"),
        True,
    )
    ctl.check(
        "VACUITY: an empty output matches no needle", scenario_passed(RC_ZERO, 0, "", "x"), False
    )

    ctl.check(
        "CONTROL: the real fixture shape is recognised as indented",
        indented_result_lines('    echo "  PASS: 900 the guard is enabled"\n'),
        True,
    )
    ctl.check(
        "CONTROL: the FAIL half is recognised too",
        indented_result_lines('    echo "  FAIL: 900 the guard is disabled"\n'),
        True,
    )
    ctl.check(
        "PLANT: a flush-left result line is NOT indented",
        indented_result_lines('echo "  PASS: 900 the guard is enabled"\n'),
        False,
    )
    ctl.check(
        "PLANT: an indented line with the wrong inner spacing does not count",
        indented_result_lines('    echo "PASS: 900 the guard is enabled"\n'),
        False,
    )
    ctl.check("VACUITY: an empty suite is not indented", indented_result_lines(""), False)

    tally = _Tally()
    tally.bad("a label", "line one\nline two")
    ctl.check("the tally counts a failure", tally.failed, 1)
    tally.ok("a passing label")
    ctl.check("...and `ok` does not", tally.failed, 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
