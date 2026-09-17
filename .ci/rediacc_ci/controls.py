"""The controls runner: a counted, floored assertion tally with one implementation.

WHAT IT REPLACES. Five files under `.claude/hooks/stop` each carry their own copy of the same eighteen lines -- a `class Tally` with two class attributes, a `control(label, got, want)` that increments them and prints to stderr, sometimes a `truthy`, sometimes a floor, then a three-line verdict block. The copies have already drifted:

  test-planfile.py          Tally + control + truthy, floor 60, "%s" formatting,
                            silent on pass
  test-judge-schema.py      Tally + control, NO floor, f-string formatting
  test-adhoc-watch.py       Tally + control, NO floor, f-string formatting
  test-plan-status-parse.py Tally + control, NO floor, f-string formatting
  test-reggate-ledger.py    Tally + `check` (a different NAME for the same
                            function), floor 18, "%s" formatting, PRINTS "ok"
                            on every pass

Three of the five have no floor at all, which is the interesting part. The floor is not decoration: it is the only thing that catches a file whose controls stopped executing. A `sys.exit()` slipped into the middle of one of these files, an exception swallowed by an outer try, a fixture that stopped producing rows -- all of them end with `0 control(s) passed` and exit 0, which the
harness reports as a green suite. test-judge-schema.py's own comment records that shape: "the script exits 0 and the harness reports ok ... control(s) passed. Two blocks were" (its sentence continues into the fix). Copies cannot be fixed once.

WHY THE FLOOR IS A REQUIRED ARGUMENT AND NOT A DEFAULT. A default of 0 is a floor that cannot fail, and this package would then have shipped the very hole it was
written to close. `Controls("name", floor=0)` is still writable -- for a suite
genuinely built at runtime -- but it has to be typed, at the call site, where a reviewer sees it.

WHY IT IS NOT pytest. It nearly is, and pytest is the runner this repo now provisions. But these are not test files in a testpath; they are programs the Stop hook and `.claude/hooks/test-hooks.sh` invoke directly, whose output shape ("N control(s) passed") the harness reads. This class keeps that contract exactly
while removing the copies. A file migrated to it is a `python3 file.py` away from
behaving as it always did -- and it is also, being an ordinary object with no global state, directly assertable FROM pytest, which is how it is proven below in `.ci/rediacc_ci/tests/test_controls.py`.

THE OUTPUT CONTRACT, pinned because a harness parses it:

    stdout on success   "<N> control(s) passed"
    stderr per failure  "FAIL  <label>: got <got!r>, wanted <want!r>"
    stderr on failure   "FAIL: <F> of <N> control(s) failed"
    stderr under floor  "FAIL  only <N> control(s) ran; the file is not being
                         executed as written"
    exit code           0 when every control passed AND the floor was met, else 1

Every one of those strings is a byte-for-byte match for what the five files already print, so migrating one changes no observable output.
"""

import re
import sys

# The floor's failure message, kept verbatim from the copies it replaces. The wording is the load-bearing part: "the file is not being executed as written" names the failure mode (controls that never ran) rather than the symptom (a small number), which is what stops the next reader from just lowering it.
_FLOOR_MESSAGE = "FAIL  only %d control(s) ran; the file is not being executed as written"


class Checker:
    """A gate's own `  PASS  ` / `  FAIL  ` selftest tally, in one place.

    WHAT IT REPLACES. Four `.ci/scripts/quality/check_*.py` gates -- `check_fetch_retry.py`, `check_git_history_depth.py`, `check_judged_rule_wiring.py` and `check_review_prompt_render.py` -- opened `selftest()` with the SAME twelve lines, down to the docstring::

        def selftest():
            # ... the same one-line docstring, in all four
            ok = True

            def check(label, cond):
                nonlocal ok
                if cond:
                    print("  PASS  %s" % label)
                else:
                    ok = False
                    print("  FAIL  %s" % label, file=sys.stderr)

    `check:ci-shape-duplication` reported it as a ten-line span across four files, the largest Python finding in the tree, once the quality family entered its corpus. Nothing in those twelve lines is per-gate: the LABELS and the CONDITIONS are, and they stay at the call site untouched.

    IT IS CALLABLE SO THE CALL SITES DO NOT MOVE. `check = Checker()` then
    `check("label", cond)` is exactly what the four files already write, at roughly a hundred call sites between them. `harness.py` makes the same argument for the ported bash vocabulary: "rewriting them all is not a consolidation, it is a rewrite with its own defect budget".

    WHY NOT `Controls` ABOVE, which is the same idea. Two reasons, and the second is the real one. `Controls` is a got/want tally whose failure line is `FAIL <label>: got <got!r>, wanted <want!r>`; these four assert a BOOLEAN, for which that message would read `got False, wanted 'something truthy'` -- the contradiction `Controls.falsy` exists to avoid, one level up. And these four
    print ` PASS <label>` on the way past, two spaces indented, which is what a reader watching `--selftest` scroll sees; `Controls` prints a count at the end. Migrating the output shape is a separate change with its own argument, and folding it in here would smuggle it past review as tidying.
    """

    def __init__(self) -> None:
        self.ok = True
        self.count = 0

    def __call__(self, label: str, cond: object) -> bool:
        self.count += 1
        if cond:
            print("  PASS  %s" % label)
            return True
        self.ok = False
        print("  FAIL  %s" % label, file=sys.stderr)
        return False


def controls_first(name: str, selftest) -> int:
    """Run a gate's own controls before its verdict. 0 to continue, 2 to refuse.

    WHAT IT REPLACES. Seven `.ci/scripts/quality/check_*.py` gates opened `main()`
    with a byte-identical six-line block, differing only in the banner's subject::

        print("actions allowlist: controls first, then the verdict")
        if selftest():
            print(
                "\u2717 instrument control failed; every verdict below would be meaningless",
                file=sys.stderr,
            )
            return 2

    The refusal sentence is word-for-word the same in all seven, because it says the same thing in all seven; only the subject is per-gate, and it stays at the call site as an argument. `check:ci-shape-duplication` reported the block as two overlapping findings, seven copies and three, once the Python quality family entered its corpus.

    `selftest` IS A CALLABLE, NOT A RESULT, so the banner is printed before the controls run rather than after. That ordering is the point of the idiom: a reader watching a gate scroll past sees which gate is talking before it says anything, and a control that hangs or crashes has already been attributed.

    RETURN 2, NOT 1, and it is not arbitrary. These gates use 1 for "the tree has a finding" and 2 for "the instrument is broken, so there is no verdict". A caller that collapsed the two would report a defective gate as a defective tree.
    """
    print("%s: controls first, then the verdict" % name)
    if selftest():
        print(
            "\u2717 instrument control failed; every verdict below would be meaningless",
            file=sys.stderr,
        )
        return 2
    return 0


class VacuousPlantError(AssertionError):
    """A control mutant that would not have differed from the clean fixture.

    An `AssertionError` and not a bespoke base, because that is what every caller's test runner already treats as a failed assertion -- which is exactly what this is.
    """


def plant(text: str, old: str, new: str, count: int = -1) -> str:
    """The clean fixture with `old` replaced by `new`, or raise.

    WHY THIS EXISTS RATHER THAN `str.replace`. A control proves a gate can fail by feeding it a mutated fixture; if the mutation silently does nothing, the gate is handed the CLEAN input, stays green, and the control reports a pass
    for an assertion it never made. That is the vacuous-control class, and
    `.ci/scripts/quality/check-control-vacuity.sh` exists to catch it -- but only on the bash side. Its own comment recorded that no Python gate built a mutant by substitution and that "what must not happen is that changing silently". It changed, from 21 gates to 50, and the alarm was a count printed inside a SUCCESS message, which nothing reads. Measured 2026-09-08: 71
    substitution sites across 12 Python gate modules, three proofs between them, and one already-vacuous mutant in the tree.

    RAISING IS THE POINT, and it is why this is not a checked return. A returned flag can be ignored by the caller who most needed it, and many of these fixtures are built at MODULE level where no `Controls` instance exists yet to record a failure against. An exception needs no receiver and cannot be dropped.

    Three separate refusals, deliberately distinguishable, because they are three different author mistakes:
      * `old` absent      -- the fixture drifted out from under the control.
      * `old == new`      -- a typo; the author meant two different strings.
      * result unchanged  -- reachable ONLY via `count=0`, which is a caller
                             typo that would otherwise return the clean fixture
                             silently. With a present needle and `old != new` a
                             replace must differ, so this arm is narrow rather
                             than belt-and-braces; it is controlled by that
                             exact case in `test_controls.py` and is not the
                             unreachable branch it first looks like.
    """
    if old == new:
        raise VacuousPlantError(
            "plant() asked to replace %r with itself: old and new are identical, so "
            "the mutant would equal the clean fixture and the control would assert "
            "nothing." % (old,)
        )
    if not old:
        raise VacuousPlantError("plant() needs a non-empty needle; '' matches everywhere.")
    if old not in text:
        raise VacuousPlantError(
            "plant() found no %r in the fixture, so no mutation happened and the "
            "control would run against CLEAN input. The fixture has probably drifted "
            "away from the needle." % (old,)
        )
    out = text.replace(old, new) if count < 0 else text.replace(old, new, count)
    if out == text:
        raise VacuousPlantError(
            "plant() produced a mutant byte-identical to the clean fixture despite "
            "finding %r; the control would assert nothing." % (old,)
        )
    return out


def plant_re(text: str, pattern: str, repl: str, flags: int = 0) -> str:
    """`plant`, for the sites that need a regex. Same three refusals.

    A SEPARATE FUNCTION rather than a mode flag on `plant`: a single entry point taking either would need a boolean at every call site, and a boolean argument that changes how the other two are interpreted is how a caller ends up passing a regex to the literal path and getting a silent no-op -- the exact failure this module exists to make impossible.
    """
    out, n = re.subn(pattern, repl, text, flags=flags)
    if n == 0:
        raise VacuousPlantError(
            "plant_re() matched %r zero times, so no mutation happened and the "
            "control would run against CLEAN input." % (pattern,)
        )
    if out == text:
        raise VacuousPlantError(
            "plant_re() matched %r %d time(s) but produced a mutant byte-identical "
            "to the clean fixture; the control would assert nothing." % (pattern, n)
        )
    return out


class Controls:
    """A counted tally of assertions with a floor under how many must run.

    Not a singleton and not a module global: two suites in one process each get their own, which is what lets the runner be tested by a test suite that is itself counting things.
    """

    def __init__(self, name: str, floor: int, *, verbose: bool = False) -> None:
        """`floor` is positional-ish on purpose; see the module docstring.

        `verbose` prints "ok <label>" per passing control, which is what test-reggate-ledger.py does and the other four do not. Both behaviours are real -- a long suite is unreadable verbose, a short one is unverifiable silent -- so it is an argument rather than a decision made
        for every caller.
        """
        if floor < 0:
            raise ValueError("floor must not be negative (got %d)" % floor)
        self.name = name
        self.floor = floor
        self.verbose = verbose
        self.count = 0
        # The LABELS of what failed, not just how many. A count tells the reader a suite is red; the labels tell them which control, which is the whole value of naming every assertion in the first place.
        self.failures: list[str] = []

    # -- the assertions ------------------------------------------------------
    #
    # Each returns the boolean, so a caller can branch on a control's outcome without re-evaluating the condition. The copies return None, and one of them works around it by recomputing the comparison in an `if` on the next line -- two expressions that must agree, which is one too many.

    def check(self, label: str, got: object, want: object) -> bool:
        """Equality. The workhorse; `control` and `check` in the copies."""
        return self._record(label, got == want, got, want)

    def truthy(self, label: str, got: object) -> bool:
        """`got` must be truthy. `truthy` in test-planfile.py."""
        return self._record(label, bool(got), got, "something truthy")

    def falsy(self, label: str, got: object) -> bool:
        """`got` must be falsy.

        Present because its absence is why the copies write `control("...", bool(x), False)`, which reports `got False, wanted False` when it fails -- a message that is literally a contradiction, produced by squeezing a one-sided assertion through a two-sided one.
        """
        return self._record(label, not got, got, "something falsy")

    def raises(self, label: str, exc: type[BaseException], fn, *args, **kwargs) -> bool:
        """`fn(*args)` must raise `exc`.

        None of the five copies has this, and all five need it: the error paths are where a gate's behaviour is least tested and most consequential, and without a helper the shape is a five-line try/except/else that people do not write. A DIFFERENT exception is not caught here -- it propagates -- because "it raised something else" is a bug in the test, not a finding.
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

        The floor is reported as a failure THROUGH the same channel as any other, so a suite that is simultaneously short and red says both things rather than the floor masking the real findings.
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
