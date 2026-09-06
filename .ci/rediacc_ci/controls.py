"""The controls runner: a counted, floored assertion tally with one implementation.

WHAT IT REPLACES. Five files under `.claude/hooks/stop` each carry their own copy
of the same eighteen lines -- a `class Tally` with two class attributes, a
`control(label, got, want)` that increments them and prints to stderr, sometimes
a `truthy`, sometimes a floor, then a three-line verdict block. The copies have
already drifted:

  test-planfile.py          Tally + control + truthy, floor 60, "%s" formatting,
                            silent on pass
  test-judge-schema.py      Tally + control, NO floor, f-string formatting
  test-adhoc-watch.py       Tally + control, NO floor, f-string formatting
  test-plan-status-parse.py Tally + control, NO floor, f-string formatting
  test-reggate-ledger.py    Tally + `check` (a different NAME for the same
                            function), floor 18, "%s" formatting, PRINTS "ok"
                            on every pass

Three of the five have no floor at all, which is the interesting part. The floor
is not decoration: it is the only thing that catches a file whose controls stopped
executing. A `sys.exit()` slipped into the middle of one of these files, an
exception swallowed by an outer try, a fixture that stopped producing rows -- all
of them end with `0 control(s) passed` and exit 0, which the harness reports as a
green suite. test-judge-schema.py's own comment records that shape: "the script
exits 0 and the harness reports ok ... control(s) passed. Two blocks were" (its
sentence continues into the fix). Copies cannot be fixed once.

WHY THE FLOOR IS A REQUIRED ARGUMENT AND NOT A DEFAULT. A default of 0 is a floor
that cannot fail, and this package would then have shipped the very hole it was
written to close. `Controls("name", floor=0)` is still writable -- for a suite
genuinely built at runtime -- but it has to be typed, at the call site, where a
reviewer sees it.

WHY IT IS NOT pytest. It nearly is, and pytest is the runner this repo now
provisions. But these are not test files in a testpath; they are programs the
Stop hook and `.claude/hooks/test-hooks.sh` invoke directly, whose output shape
("N control(s) passed") the harness reads. This class keeps that contract exactly
while removing the copies. A file migrated to it is a `python3 file.py` away from
behaving as it always did -- and it is also, being an ordinary object with no
global state, directly assertable FROM pytest, which is how it is proven below in
`.ci/rediacc_ci/tests/test_controls.py`.

THE OUTPUT CONTRACT, pinned because a harness parses it:

    stdout on success   "<N> control(s) passed"
    stderr per failure  "FAIL  <label>: got <got!r>, wanted <want!r>"
    stderr on failure   "FAIL: <F> of <N> control(s) failed"
    stderr under floor  "FAIL  only <N> control(s) ran; the file is not being
                         executed as written"
    exit code           0 when every control passed AND the floor was met, else 1

Every one of those strings is a byte-for-byte match for what the five files
already print, so migrating one changes no observable output.
"""

import sys

# The floor's failure message, kept verbatim from the copies it replaces. The
# wording is the load-bearing part: "the file is not being executed as written"
# names the failure mode (controls that never ran) rather than the symptom (a
# small number), which is what stops the next reader from just lowering it.
_FLOOR_MESSAGE = "FAIL  only %d control(s) ran; the file is not being executed as written"


class Controls:
    """A counted tally of assertions with a floor under how many must run.

    Not a singleton and not a module global: two suites in one process each get
    their own, which is what lets the runner be tested by a test suite that is
    itself counting things.
    """

    def __init__(self, name: str, floor: int, *, verbose: bool = False) -> None:
        """`floor` is positional-ish on purpose; see the module docstring.

        `verbose` prints "ok    <label>" per passing control, which is what
        test-reggate-ledger.py does and the other four do not. Both behaviours
        are real -- a long suite is unreadable verbose, a short one is
        unverifiable silent -- so it is an argument rather than a decision made
        for every caller.
        """
        if floor < 0:
            raise ValueError("floor must not be negative (got %d)" % floor)
        self.name = name
        self.floor = floor
        self.verbose = verbose
        self.count = 0
        # The LABELS of what failed, not just how many. A count tells the reader
        # a suite is red; the labels tell them which control, which is the whole
        # value of naming every assertion in the first place.
        self.failures: list[str] = []

    # -- the assertions ------------------------------------------------------
    #
    # Each returns the boolean, so a caller can branch on a control's outcome
    # without re-evaluating the condition. The copies return None, and one of
    # them works around it by recomputing the comparison in an `if` on the next
    # line -- two expressions that must agree, which is one too many.

    def check(self, label: str, got: object, want: object) -> bool:
        """Equality. The workhorse; `control` and `check` in the copies."""
        return self._record(label, got == want, got, want)

    def truthy(self, label: str, got: object) -> bool:
        """`got` must be truthy. `truthy` in test-planfile.py."""
        return self._record(label, bool(got), got, "something truthy")

    def falsy(self, label: str, got: object) -> bool:
        """`got` must be falsy.

        Present because its absence is why the copies write
        `control("...", bool(x), False)`, which reports `got False, wanted False`
        when it fails -- a message that is literally a contradiction, produced by
        squeezing a one-sided assertion through a two-sided one.
        """
        return self._record(label, not got, got, "something falsy")

    def raises(self, label: str, exc: type[BaseException], fn, *args, **kwargs) -> bool:
        """`fn(*args)` must raise `exc`.

        None of the five copies has this, and all five need it: the error paths
        are where a gate's behaviour is least tested and most consequential, and
        without a helper the shape is a five-line try/except/else that people do
        not write. A DIFFERENT exception is not caught here -- it propagates --
        because "it raised something else" is a bug in the test, not a finding.
        """
        try:
            fn(*args, **kwargs)
        except exc as caught:
            return self._record(label, True, type(caught).__name__, exc.__name__)
        return self._record(label, False, "no exception", exc.__name__)

    def fail(self, label: str, detail: object = "") -> bool:
        """Record a failure directly, for a condition no helper expresses."""
        return self._record(label, False, detail, "no failure")

    def _record(self, label: str, ok: bool, got: object, want: object) -> bool:
        self.count += 1
        if ok:
            if self.verbose:
                print("ok    %s" % label)
            return True
        self.failures.append(label)
        print("FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)
        return False

    # -- the verdict ---------------------------------------------------------

    @property
    def floor_met(self) -> bool:
        return self.count >= self.floor

    @property
    def ok(self) -> bool:
        """Green means BOTH: nothing failed AND enough controls actually ran."""
        return not self.failures and self.floor_met

    def report(self) -> bool:
        """Print the verdict. Returns True when green. Safe to call once.

        The floor is reported as a failure THROUGH the same channel as any other,
        so a suite that is simultaneously short and red says both things rather
        than the floor masking the real findings.
        """
        if not self.floor_met:
            self.failures.append("floor:%d" % self.floor)
            print(_FLOOR_MESSAGE % self.count, file=sys.stderr)
        if self.failures:
            print(
                "FAIL: %d of %d control(s) failed" % (len(self.failures), self.count),
                file=sys.stderr,
            )
            return False
        print("%d control(s) passed" % self.count)
        return True

    def exit(self) -> None:
        """`report()` then `sys.exit`. The last line of a migrated file."""
        sys.exit(0 if self.report() else 1)
