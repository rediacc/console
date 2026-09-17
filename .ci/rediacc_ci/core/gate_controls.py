"""The shell gate control-tally, ported from `.ci/scripts/lib/gate-controls.sh`.

PORTED FROM `.ci/scripts/lib/gate-controls.sh` (41 lines), which still exists and
is still sourced by three quality gates plus one test helper. This module does
NOT shim it: per the box that produced it, deletion and cutover are a later
step, so both implementations are live and the differential in
`.ci/rediacc_ci/tests/test_core_gate_controls.py` is what says they agree.

WHY IT IS WORTH PORTING AT ALL, WHICH IS NOT THE 41 LINES. `gate-controls.sh`
was extracted on 2026-09-06 after `check:ci-shape-duplication` caught the same
five lines in three files. The SAME shape has since been re-created three times
in Python, and the copies say so themselves:

  .ci/rediacc_ci/quality/release_signing_coverage.py:62  "THE TALLY IS A LOCAL
                                                          COPY OF gate-controls.sh,
                                                          AND THAT IS DELIBERATE."
  .ci/rediacc_ci/quality/release_key_canonical.py:175    "gate-controls.sh,
                                                          transliterated byte for byte."
  .ci/rediacc_ci/quality/staging_tag_guard.py:158        the same sentence again.

Three copies is exactly the count that made the bash extraction correct, so the
Python side has arrived back at the state the bash side left. This module is the
one implementation those three can eventually reach. REPOINTING THEM IS NOT DONE
HERE and is not this module's licence to grant: they are gates with their own
recorded shadow ledgers, and a body swap under a ledger is a separate change.

WHY NOT `rediacc_ci.controls.Controls`, WHICH IS THE SAME IDEA. It is a different
OUTPUT CONTRACT, and the contract is the thing a caller depends on:

                        gate-controls.sh / this module   controls.Controls
  pass line             `  ok    <label>` (stdout)       silent, or `ok    <label>`
  fail line             `  FAIL  <label> (got 'a'        `FAIL  <label>: got 'a',
                        want 'b')` (stderr)              wanted 'b'` (stderr)
  floor line            `...the battery is not being     `...the file is not being
                        executed as written`             executed as written`
  verdict on green      `✓ <subject>: <N> control(s)     `<N> control(s) passed`
                        passed`
  verdict on red        `✗ <subject>: <F> of <N>         `FAIL: <F> of <N>
                        control(s) failed`               control(s) failed`

"battery" versus "file" is not a synonym here: a reader greps for one or the
other. `.ci/rediacc_ci/tests/test_quality_release_signing_coverage.py:201`
already records the split in as many words. Two vocabularies with two live
reader populations is a merge with its own argument, and folding it in here
would smuggle that argument past review as tidying.

THE FLOOR IS THE WHOLE POINT, and it is why this file is not a convenience. A
battery that did not run is not a green one. `gate_finish` counts the controls
that actually executed and refuses under the floor, which is the only thing that
catches a gate whose assertions stopped running -- an early `return`, a fixture
that produced no rows, a loop over an empty list. Every one of those otherwise
ends with a clean exit and no output that says anything is wrong.

THE GLOBALS ARE PART OF THE PORT, NOT AN ACCIDENT. `GATE_FAILS` and `GATE_N` are
bash globals shared by everything sourced into one shell, so `MODULE_TALLY` below
is a module-level singleton with `gate_check` / `gate_finish` as free functions
bound to it. That is the literal translation and it is what the entry point
drives. A caller who wants two independent tallies in one process constructs
`GateTally()` directly, which bash cannot do and is the one capability the port
adds.

`gate_finish` IS NOT IDEMPOTENT, IN EITHER LANGUAGE. Under the floor it APPENDS a
failure to the tally, so calling it twice on a short battery reports two. The
bash does the same (`GATE_FAILS=$((GATE_FAILS + 1))` inside the `if`), and a port
that quietly fixed it would disagree with the twin on a real input. It is pinned
by a case rather than corrected.

THE ENTRY POINT reads a US-separated program on stdin so a differential can hand
the same bytes to both sides:

    check<US><label><US><got><US><want>
    finish<US><min><US><subject>

THE FIELD SEPARATOR IS US (`\x1f`), NOT TAB, AND THAT IS A BUG THIS FILE ALREADY
PAID FOR. The first draft used tab. TAB IS IFS WHITESPACE IN BASH, so `IFS=$'\t'
read -r a b c` COLLAPSES consecutive tabs into one delimiter and an empty field
simply disappears, shifting every later field left. Measured on the first run of
this differential: a case with an empty `name` made the bash side read the FIX
hint as the name and print a different header, and the comparator reported a
STDOUT-DIFF that looked exactly like a port defect. It was a defect in the
DRIVER. `\x1f` is not IFS whitespace, so empty fields survive on both sides, and
an empty field is a case this contract has to be able to express.

Zero lines of program is a REFUSAL (exit 2), not an empty green: a driver that
fed nothing would otherwise get `✓ ...: 0 control(s) passed` out of a floor of
zero, which is the exact vacuity the floor exists to prevent, manufactured one
level up.
"""

import sys

# The four literals, kept as constants because the differential and the three Python copies all match on them and a typo in any one of them is invisible in a passing test that greps for the wrong string.
OK_LINE = "  ok    %s"
FAIL_LINE = "  FAIL  %s (got '%s' want '%s')"
FLOOR_LINE = "FAIL  only %d control(s) ran; the battery is not being executed as written"
RED_VERDICT = "✗ %s: %d of %d control(s) failed"
GREEN_VERDICT = "✓ %s: %d control(s) passed"

SEP = "\x1f"

USAGE = """gate_controls -- the `gate-controls.sh` tally, driven from stdin.

  printf 'check\\x1flabel\\x1fgot\\x1fwant\\nfinish\\x1f1\\x1fsubject\\n' \\
      | python3 -m rediacc_ci.core.gate_controls

Program lines, separated by US (0x1f, NOT tab -- see the module docstring):
  check   <label> <got> <want>    one control
  finish  <min>   <subject>       the floor, then the verdict

Exit: 0 green, 1 red or under the floor, 2 the program itself was unusable.
"""


class GateTally:
    """A counted tally with a floor, printing `gate-controls.sh`'s exact bytes.

    Not a module global on the class: two tallies in one process each get their
    own counters, which is what lets this be tested by a test suite that is
    itself counting things. The module-level `MODULE_TALLY` below is the literal
    translation of the bash globals, for callers that want that.
    """

    def __init__(self) -> None:
        self.fails = 0
        self.n = 0

    def check(self, label: str, got: object, want: object) -> bool:
        """`gate_check`. STRING equality, because `[[ "$2" == "$3" ]]` is.

        The comparison is on `str(got)` and `str(want)` rather than on the
        objects: bash has only strings, so `check("n", 1, "1")` must PASS here
        or the port disagrees with the twin the first time a caller passes an
        int. Returns the boolean so a caller can branch without recomputing the
        comparison, which is the one thing the bash cannot offer.
        """
        self.n += 1
        got_s, want_s = str(got), str(want)
        if got_s == want_s:
            print(OK_LINE % label)
            return True
        self.fails += 1
        print(FAIL_LINE % (label, got_s, want_s), file=sys.stderr)
        return False

    def finish(self, minimum: int, subject: str) -> int:
        """`gate_finish`. The floor, then the verdict. Returns the exit code.

        Returns an int rather than a bool because the bash returns an exit
        status and every caller of this port is deciding an exit status. A bool
        would invert at exactly one call site and be right everywhere else,
        which is the worst way for it to be wrong.
        """
        if self.n < minimum:
            print(FLOOR_LINE % self.n, file=sys.stderr)
            self.fails += 1
        if self.fails:
            print(RED_VERDICT % (subject, self.fails, self.n), file=sys.stderr)
            return 1
        print(GREEN_VERDICT % (subject, self.n))
        return 0


# The bash globals, in the one shape bash has. `source gate-controls.sh` puts
# GATE_FAILS and GATE_N in the shell; importing this module puts MODULE_TALLY in
# the interpreter. Same lifetime, same sharing, same hazard.
MODULE_TALLY = GateTally()


def gate_check(label: str, got: object, want: object) -> bool:
    """`gate_check`, against the process-wide tally."""
    return MODULE_TALLY.check(label, got, want)


def gate_finish(minimum: int, subject: str) -> int:
    """`gate_finish`, against the process-wide tally."""
    return MODULE_TALLY.finish(minimum, subject)


def reset() -> None:
    """Zero the process-wide tally. For tests; bash has no equivalent."""
    MODULE_TALLY.fails = 0
    MODULE_TALLY.n = 0


def run_program(lines: list[str], tally: GateTally | None = None) -> int:
    """Interpret the US-separated program. Exit code, or 2 for a bad program.

    A MALFORMED LINE IS A REFUSAL, NOT A SKIP. A driver that mistypes `chekc`
    would otherwise contribute nothing to the tally and the floor would report
    "the battery is not being executed as written" -- true, but naming the wrong
    cause, and the reader would go looking at the gate instead of at the typo.
    """
    tally = GateTally() if tally is None else tally
    program = [line for line in lines if line.strip()]
    if not program:
        print(
            "gate_controls: the program was empty, so no control ran and no verdict\n"
            "  is available. An empty program is a broken driver, not a green gate.",
            file=sys.stderr,
        )
        return 2
    saw_finish = False
    code = 0
    for raw in program:
        fields = raw.rstrip("\n").split(SEP)
        verb = fields[0]
        if verb == "check":
            if len(fields) != 4:
                print(
                    "gate_controls: `check` needs exactly label, got, want (3 US-separated\n"
                    "  fields after the verb); this line had %d." % (len(fields) - 1),
                    file=sys.stderr,
                )
                return 2
            tally.check(fields[1], fields[2], fields[3])
        elif verb == "finish":
            if len(fields) != 3 or not fields[1].lstrip("-").isdigit():
                print(
                    "gate_controls: `finish` needs an integer floor and a subject.",
                    file=sys.stderr,
                )
                return 2
            saw_finish = True
            code = tally.finish(int(fields[1]), fields[2])
        else:
            print(
                "gate_controls: unknown verb %r; the program understands `check` and\n"
                "  `finish` only." % (verb,),
                file=sys.stderr,
            )
            return 2
    if not saw_finish:
        print(
            "gate_controls: the program ran %d control(s) and never called `finish`,\n"
            "  so nothing rendered a verdict. That is a driver bug, not a pass." % (tally.n,),
            file=sys.stderr,
        )
        return 2
    return code


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0
    return run_program(sys.stdin.read().splitlines())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
