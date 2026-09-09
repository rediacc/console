#!/usr/bin/env python3
"""Run the rediacc_ci suite, and refuse to call a collapsed collection green.

WHAT THIS GATE IS FOR. `pytest` on its own is not a gate. Point it at a directory
that no longer exists, mistype `testpaths`, break an import in a conftest, and it
prints `no tests ran` and exits 5 -- or, worse, collects a handful of the files it
can still see and exits 0. A wrapper that only forwards pytest's exit code turns
the second case into a green CI step forever, which is the same failure
`.ci/scripts/quality/check-python-lint.sh` documents for `ruff check` with an
empty file list, and the same one `test-gate-anti-vacuity.sh` exists to catch
across the whole battery.

So this refuses on three separate grounds before it will report a pass:

  1. THE CORPUS ITSELF. `MIN_TESTS` test functions must EXIST in the test files
     on disk. Below that the tests have been deleted or the directory has moved,
     and every count derived from them is meaningless.
  2. THE COLLECTION. pytest must collect at least as many tests as the corpus
     contains. This is the floor that actually catches things: an import error in
     one module, a `python_files` mismatch, a fixture that raises at collection
     time all reduce the collected count while leaving the files in place.
  3. THE RESULT. Every collected test must pass.

WHY TWO FLOORS AND NOT ONE, since docs/ci-overhaul/08-driver-contract.md section
6 rules that a floor must be corpus-derived rather than hand-typed. Floor 2 IS
corpus-derived and is the primary: it re-keys itself as tests are added and
removed, so a correct rename never reds it. But a corpus-derived floor has one
hole, and it is the hole that matters most -- if the test DIRECTORY disappears,
the corpus is 0, the derived floor is 0, and `0 >= 0` reports green. Floor 1 is
the base case under that recursion: a constant is the only thing that can catch
the corpus itself vanishing. It is stated here, with its size argued, rather than
being the whole design.

WHY `MIN_TESTS` IS 150 AND NOT 1. Sized to roughly two thirds of the corpus, so
a legitimate consolidation has room and a HALF-broken glob does not. It read 40
against phase 2's 65 test functions; phase 3 landed `log`, `proc`, `gitx` and
`workflows` with their differentials and the corpus is 187 across six modules, so
the floor is re-sized in the same commit rather than left behind at a number that
one module's tests would satisfy on their own. That is the whole hazard a
constant floor exists for: it only works while it is proportionate.

This is the same reasoning, and the same shape, as `MIN_PY_FILES=10` in
check-python-lint.sh. Raise it when the suite grows; a deliberate REMOVAL of most
of this package's tests should have to edit this line and say why.

EXIT CODES, AND THE ONE DISTINCTION THAT MATTERS.

    0   the suite ran, collected enough, and passed
    1   a real verdict: a test failed, or a floor was not met
    77  pytest is NOT AVAILABLE, so no verdict was reached at all

77 is this repo's "could not run", classified by the ci-runner as BLOCKED --
counted, named and warned about, but never a judgement on the code. It exists
because exit 1 here would say "the tests failed", which is false, and which made
a pre-push lane refuse every push on a machine that simply lacked the tool. It is
NOT a skip and NOT softer: under CI the bootstrap has run, so 77 never fires
there; if it ever did, the workflow sees a plain non-zero and the lane is broken,
which is correct.

A CONFIG ERROR IS NOT A 77. pytest exiting 4 (usage error) means this repo's own
`[tool.pytest.ini_options]` is wrong, which is a defect in the tree and gets a 1.
The line between the two is "is the tool here", not "did the tool complain".

HOW pytest IS FOUND. It is not resolved here. `.ci/bootstrap.sh doctor` already
implements the three-rung ladder -- $PYTEST_BIN, then a PATH binary AT THE PIN,
then the repo-local install under .ci/cache/ -- and its rungs are themselves
lifted from `resolve_ruff` in check-python-lint.sh. This parses that report
rather than growing a fourth copy of the ladder, so $PYTEST_BIN and the pin are
honoured here for free and cannot drift from what the bootstrap installs.

    .ci/rediacc_ci/check_pytest.py              run the suite and judge it
    .ci/rediacc_ci/check_pytest.py --selftest   prove this gate can fail

NOT YET REGISTERED. There is no `---- gate ----` header in this file on purpose:
`scripts/gate-bind.ts` only scans `.ci/scripts/` and `scripts/` (its `inScope`
regex is `^(\\.ci\\/scripts|scripts)\\/`), so a header here would be inert -- a
declaration that reads as wired and is not. Registration is the root driver's,
via package.json, scripts/ci-runner/manifest.ts and the workflow.
"""

import ast
import os
import pathlib
import re
import sys
import tempfile
import time
import tomllib

# THE HOP, WRITTEN BY HAND EXACTLY ONCE. This file is a script, so it cannot
# import the module that would put its own package on sys.path until its package
# is on sys.path. Everything after this line goes through rediacc_ci.paths.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from rediacc_ci import paths, proc
from rediacc_ci.controls import Controls

# See the module docstring for why this is a constant and floor 2 is not.
MIN_TESTS = 150
# HOW LONG THE SUITE MAY TAKE BEFORE THIS GATE REFUSES, and it is a refusal rather
# than a crash: see the TimeoutExpired arm in run_pytest.
#
# 900 was the value until 2026-09-07, chosen when the corpus was small. That day it
# measured 810.16s -- 90 seconds of margin -- while the corpus grew from 318s to
# 675s in a single day and gains about 200 tests per gate-test port batch. The
# number is now sized against a MEASURED floor with real headroom, not against the
# last run that happened to fit, and it is a module constant so raising it is one
# visible edit rather than a literal buried in a call.
#
# 2400 -> 3600 on 2026-09-08, and the CAUSE is named because the number alone
# would look like drift. `test-claude-hooks.sh` became portable that day
# (`TWIN_TIMEOUT` in `.ci/rediacc_ci/tests/gates/test_twin_parity.py` replaced a
# hardcoded 600s that had made any slow twin unportable by construction). It runs
# 2 229 offline cases in 13m31s and now costs this suite THREE times: the ported
# module itself, plus `test_twin_parity` driving the bash twin, plus the same
# parity case driving the port. Measured immediately after: 1879s against a 2400s
# kill timer -- 78% of it, where the previous baseline was 381s.
#
# RAISING THE KILL TIMER IS NOT THE FIX, and must not be mistaken for one. It
# stops a spurious kill reporting as a gate failure; it does nothing about a
# 31-minute gate. The real options are to re-tier the claude-hooks parity case
# into its own lane, or to split that harness so no single subject is billed
# three times. Both are larger than this line and are tracked as findings.
#
# 3600 -> 1080 THE SAME DAY, because 3600 COULD NOT FIRE. This gate runs as the
# `Python package tests` step of `quality-security` in `ci-quality.yml`, and that
# job declares `timeout-minutes: 20` -- 1200s. An in-script kill timer above its
# own job's ceiling is dead code in CI: GitHub cancels the job first, and a
# cancelled job's only clue is `The operation was canceled.` with no verdict, no
# KILLED line, and no named cause. That is the exact chain
# `check_job_timeout_headroom.py` was written for, one level down, where that
# gate cannot see it -- it reads workflow ceilings, never in-script timers.
#
# 1080 = 18 minutes: above the 810.16s the suite measured on 2026-09-07 with real
# margin, and below the 1200s ceiling with two minutes left for the rest of the
# job. Under it, a suite that overruns is KILLED by this gate WITH its diagnostic
# instead of vanishing into an opaque cancel. It does not make the suite faster
# and is not pretending to: if the run genuinely needs longer than the job allows,
# the job's `timeout-minutes` is the number to argue about, not this one.
# `check:ci-inner-timeout-reachable` now enforces the relationship.
RUN_TIMEOUT_S = int(os.environ.get("PYTEST_RUN_TIMEOUT_S") or 1080)

# HOW MANY WORKERS, and it is not `auto`. `-n auto` takes every core (24 here)
# and oversubscribes against the ci-runner's own 22-slot pool, which is already
# running 356 other gates. The shape and the reason are copied from
# `battery._default_jobs` rather than re-derived.
#
# `-n` AND `weight` MOVE TOGETHER. `pool.ts:242` caps effective weight at the
# pool size, so `weight: 8` reads as "the whole pool" on a 2-slot CI runner and
# as 8 of 22 locally. An `-n` larger than the declared weight is an undeclared
# claim on the machine, which is how a parallel gate makes a lane SLOWER.
#
# WHY 8 AND NOT MORE, measured on the full corpus: serial 823.93s; `-n 8` with
# working groups 381.41s (2.16x); `-n 16` 377.18s. Sixteen buys nothing, because
# the floor is now the 294.65s guards fixture pinned to a single worker. Raising
# this number is pointless until that driver is parallelised internally.
PYTEST_JOBS_CAP = 8


def jobs() -> int:
    """Worker count for the parallel run. PYTEST_JOBS overrides; 1 is serial."""
    override = os.environ.get("PYTEST_JOBS")
    if override and override.isdigit() and int(override) > 0:
        return int(override)
    return max(1, min(PYTEST_JOBS_CAP, os.cpu_count() or 1))


# Mirrors `python_files` in the root pyproject.toml. Pinned to one form there so
# the corpus count below and pytest's own collection cannot disagree about which
# files are in scope.
TEST_GLOB = "test_*.py"

# A test FUNCTION at module level. The anchor is the FALLBACK, not the primary,
# and the comment here used to claim it was enough: "anchored so a `def test_`
# inside a docstring or a nested helper does not inflate the count". It is not.
# `re.MULTILINE` anchors to a LINE, and a triple-quoted fixture holding a sample
# module writes its `def test_one(gate):` at column 0 like any other line, so the
# regex counts it. Measured 2026-09-08 across all three testpaths: 2228 by regex
# against 2216 real functions, 12 phantoms in the two gate tests that carry
# synthetic Python fixtures. Harmless that day only because parametrisation put
# collection at 3371, far above either number -- the floor is `collected >=
# corpus`, so an INFLATED corpus is a gate that reds for no reason, and it was 12
# fixtures away from doing so.
TEST_DEF_RE = re.compile(r"^def (test_\w+)\s*\(", re.MULTILINE)

# pytest's own report lines. The collection count comes from the header, `N passed`
# from the summary. Both are parsed because they answer different questions: how
# many the collector FOUND, and how many actually ran to a pass.
#
# THE COLLECTION HEADER HAS TWO SPELLINGS, AND THIS IS THE UNION OF THEM. Under
# pytest-xdist the CONTROLLER does not collect: each worker collects, and the
# header changes shape entirely. Measured on this tree, 2026-09-07, pytest 9.1.1
# with xdist 3.8.0, all three byte-for-byte:
#
#   serial   collected 30 items
#   -n 1     1 worker [30 items]
#   -n 2     2 workers [30 items]
#
# THE SERIAL LINE IS NOT MERELY MOVED, IT IS GONE: an `-n` run prints no
# `collected` line anywhere. Matching only the first spelling therefore returns
# None the moment the gate is parallelised, `verdict` says "pytest printed no
# collection line", and the gate fails naming a problem that does not exist while
# a perfectly healthy suite is running. That is the exact mystery red this union
# exists to prevent, and it is why the second alternative landed BEFORE any `-n`
# reached the argv.
#
# The worker alternative is ANCHORED with re.MULTILINE and the serial one is not.
# The serial spelling was unanchored before this change and stays that way, so
# nothing that used to parse stops parsing; the worker spelling has to be
# anchored, because `\d+ workers \[` is a shape a traceback or a failure message
# could easily contain mid-line, and a count read out of prose is worse than no
# count at all.
COLLECTED_RE = re.compile(
    r"collected (\d+) items?"
    r"|^(\d+) workers? \[(\d+) items?\]",
    re.MULTILINE,
)
PASSED_RE = re.compile(r"(\d+) passed")

# The `pytest` row of `.ci/bootstrap.sh doctor`: name, pinned version, resolved
# path. ANSI is stripped before matching, because doctor colours the ABSENT
# marker and a colour code inside the field would be captured as part of a path.
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CANNOT_RUN = 77


def _colours():
    """Empty strings under CI, so a log file does not carry escape sequences."""
    if os.environ.get("CI") == "true" or not sys.stdout.isatty():
        return "", "", ""
    return "\033[0;31m", "\033[0;32m", "\033[0m"


RED, GREEN, NC = _colours()


def corpus_test_count(tests_dir: pathlib.Path) -> int:
    """How many test functions EXIST on disk under `tests_dir`.

    Reads the files rather than asking pytest, on purpose: this number is what
    pytest's answer is checked AGAINST, so deriving it from pytest would make the
    comparison a tautology -- the exact "check that cannot fail" shape
    check-python-lint.sh records having introduced once in a control.

    PARSED WHEN IT PARSES, MATCHED WHEN IT DOES NOT. The old objection to an AST
    walk was sound -- "a floor that needs an AST walk to compute is a floor that
    can fail for its own reasons" -- and it is answered by falling back rather
    than by staying inexact: a file that will not parse is counted by the regex
    exactly as before, so the floor still cannot fail for its own reasons, while
    every file that DOES parse is counted exactly. Reading the file is still the
    point; only the way the text is read has changed, so nothing here asks pytest
    anything and the comparison stays a real one.
    """
    total = 0
    for path in sorted(tests_dir.glob(TEST_GLOB)):
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total += count_test_defs(body)
    return total


def count_test_defs(body: str) -> int:
    """Test functions really DEFINED in `body`; a string literal is not one."""
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return len(TEST_DEF_RE.findall(body))

    # WHAT PYTEST ACTUALLY COLLECTS, which is neither "every `def test_`" nor
    # "every line starting with `def test_`": a function at MODULE level, or a
    # method of a `Test*` class. An `ast.walk` would also find a def nested inside
    # another function -- pytest never collects that, and counting it inflates the
    # floor exactly as the string fixtures did. The old regex got this one right
    # by accident, through the `^` anchor, so the parse must not lose it.
    def _named(nodes: list[ast.stmt]) -> int:
        return sum(
            1
            for n in nodes
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
        )

    total = _named(tree.body)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            total += _named(node.body)
    return total


def parse_counts(text: str) -> tuple[int | None, int | None]:
    """(collected, passed) from pytest's output; None for either it did not say.

    None rather than 0 for "not stated", because the two mean opposite things: a
    run that never printed a collection line did not get far enough to have one,
    while a run that collected zero got all the way there and found nothing. A
    zero substituted for the first turns a crashed pytest into a floor failure,
    which reports the wrong problem.
    """
    collected = COLLECTED_RE.search(text)
    passed = PASSED_RE.search(text)
    # WHICHEVER ALTERNATIVE MATCHED. Group 1 is the serial count, group 3 the
    # worker-header one; group 2 is the worker COUNT and is deliberately not
    # returned here, because this function answers "how many tests", not "how
    # many processes".
    #
    # `is not None` rather than `or`, and that is not style: a genuine collection
    # of ZERO makes group(1) the string "0", which is falsy, so `group(1) or
    # group(3)` would fall through to None and crash int() -- turning the single
    # most important refusal this gate makes (exit 0 having collected nothing)
    # into a traceback.
    count = None
    if collected is not None:
        count = collected.group(1) if collected.group(1) is not None else collected.group(3)
    return (
        int(count) if count is not None else None,
        int(passed.group(1)) if passed else None,
    )


def verdict(*, corpus: int, collected: int | None, passed: int | None, returncode: int) -> str:
    """The whole decision, as a pure function of four numbers. "" means green.

    PURE ON PURPOSE. Every refusal this gate can make is decided here, so the
    selftest can exercise the entire matrix -- including combinations that are
    hard to produce for real, like `pytest exited 0 having collected nothing` --
    without running pytest at all.
    """
    if collected is None:
        return (
            "pytest printed no collection line, so it did not get far enough to have "
            "a verdict. Treating that as a pass would be reporting on a run that did "
            "not happen."
        )
    if corpus < MIN_TESTS:
        return (
            "only %d test function(s) exist on disk, floor %d. The suite has been "
            "deleted or the directory has moved; every count derived from it is "
            "meaningless, including the collection floor, which would be 0 and "
            "therefore satisfied by collecting nothing." % (corpus, MIN_TESTS)
        )
    if collected < corpus:
        return (
            "pytest collected %d test(s) but %d exist on disk. Something is failing to "
            "import or is not being collected, and a partial collection that passes "
            "reads exactly like a clean run." % (collected, corpus)
        )
    if returncode != EXIT_OK:
        # THIS GATE IS THE LIKELIEST IN THE ESTATE TO BE KILLED rather than to
        # fail: it runs ~1900s against a 3600s kill timer, so a signal here means
        # a deadline fired, not that a test failed. Reporting it as a plain exit
        # sends the reader hunting a red test that does not exist.
        sig = -returncode if returncode < 0 else (returncode - 128 if 128 < returncode < 160 else 0)
        if sig:
            return (
                "pytest was KILLED by signal %d (exit %d), so no test verdict was "
                "reached. Something terminated the run -- usually RUN_TIMEOUT_S "
                "(%ds) or an outer deadline shorter than it. Do not read this as a "
                "failing test." % (sig, returncode, RUN_TIMEOUT_S)
            )
        return "pytest exited %d." % returncode
    if passed != collected:
        return (
            "pytest exited 0 but reports %s passed out of %d collected. A skipped or "
            "deselected test is not a passing one, and the difference is invisible in "
            "the exit code." % ("no" if passed is None else str(passed), collected)
        )
    return ""


# How long `.ci/bootstrap.sh doctor` may take before this gate refuses. Named
# rather than inline so `check:ci-inner-timeout-reachable` can see it, and sized
# far below the 20-minute job ceiling this gate sits under.
DOCTOR_TIMEOUT_S = 120


def resolve_pytest(root: pathlib.Path) -> str | None:
    """The pytest binary the bootstrap resolves, or None.

    ONE LADDER, NOT A FOURTH COPY. `.ci/bootstrap.sh doctor` already implements
    $PYTEST_BIN -> a PATH binary at the pin -> the repo-local install, and
    reports what it resolved. Re-implementing those rungs in Python would be a
    second thing to drift, and the drift would be silent: both copies would find
    SOME pytest, just not the same one.
    """
    bootstrap = root / ".ci" / "bootstrap.sh"
    if not bootstrap.is_file():
        return None
    # THE TIMEOUT HAS TO KILL A PROCESS GROUP, NOT A CHILD. This was
    # `subprocess.run(..., capture_output=True, timeout=120)`, which looks bounded
    # and is not: on timeout `run` kills the direct child and then blocks in
    # `communicate()` waiting for the read ends to close, and a GRANDCHILD the
    # bootstrap spawned still holds them. Measured 2026-09-08:
    # `timeout 20 .ci/rediacc_ci/check_pytest.py --help </dev/null` exited 124
    # having written ZERO bytes to stdout AND stderr.
    #
    # WHY THAT MATTERS MORE THAN A SLOW GATE. This is `check:ci-pytest`, whose job
    # ceiling is 20 minutes. A CI run that cannot resolve pytest therefore does not
    # report "cannot run" -- it produces nothing at all until GitHub cancels the
    # job, and the only artefact is `The operation was canceled.` That is the same
    # chain `check_job_timeout_headroom.py` and `check:ci-inner-timeout-reachable`
    # exist to close, arriving through a third door.
    #
    # `start_new_session=True` puts the bootstrap in its own process group so the
    # kill reaches every descendant; `stdin=DEVNULL` closes the other way this can
    # hang, a child that decides to read from the terminal.
    # THROUGH `proc.run`, WHICH ALREADY SOLVES THIS. The first fix here hand-rolled
    # a process-group kill beside `subprocess.run`; `.ci/rediacc_ci/proc.py` had
    # carried one since it was written (`_kill(proc, group)` at :199,
    # `start_new_session=kill_group` at :256), and a second copy is how the two
    # drift. `proc.run` gives stdin=DEVNULL, a bounded wait, and a group kill that
    # reaches the grandchild still holding the read end.
    #
    # THE BUG IT REPLACES, measured 2026-09-08: `subprocess.run(...,
    # capture_output=True, timeout=120)` looks bounded and is not. On timeout it
    # kills the direct child and then blocks in `communicate()` on pipes a
    # GRANDCHILD holds, so `timeout 20 check_pytest.py --help </dev/null` exited
    # 124 having written ZERO bytes to stdout AND stderr. Under a 20-minute job
    # ceiling that surfaces only as `The operation was canceled.`
    result = proc.run(
        ["bash", str(bootstrap), "doctor"],
        cwd=str(root),
        timeout=DOCTOR_TIMEOUT_S,
    )
    if result.timed_out:
        print(
            "%s✗%s `.ci/bootstrap.sh doctor` did not answer within %ds, so pytest could\n"
            "  not be resolved. Its process group was killed. This gate refuses rather\n"
            "  than hanging to the job ceiling, where the only symptom would be\n"
            "  `The operation was canceled.` with no output at all." % (RED, NC, DOCTOR_TIMEOUT_S),
            file=sys.stderr,
        )
        return None
    stdout = result.stdout
    for line in ANSI_RE.sub("", stdout).splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "pytest":
            candidate = fields[2]
            # ABSENT is a word, not a path. Checking executability rather than
            # matching the word means a doctor that changes its wording cannot
            # quietly turn a missing tool into an attempted exec.
            if os.path.isabs(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def cannot_run(reason: str) -> int:
    """Print the 77 advice and return 77. Never 0, and never 1."""
    print("%serror%s: %s" % (RED, NC, reason), file=sys.stderr)
    print("  install the Python toolchain first:", file=sys.stderr)
    print("    bash .ci/bootstrap.sh            # installs uv, then pytest", file=sys.stderr)
    print("    bash .ci/bootstrap.sh doctor     # shows what resolved", file=sys.stderr)
    print("  or point PYTEST_BIN at an existing binary:", file=sys.stderr)
    print("    PYTEST_BIN=/path/to/pytest .ci/rediacc_ci/check_pytest.py", file=sys.stderr)
    print(
        "  NOT skipping: exit 77 means NO VERDICT was reached, which the ci-runner\n"
        "  classifies as BLOCKED. A test runner that cannot run is a gate that\n"
        "  cannot fail, and reporting 0 here would say the suite passed.",
        file=sys.stderr,
    )
    return EXIT_CANNOT_RUN


def run_pytest(pytest_bin: str, cwd: pathlib.Path, args: list[str] | None = None):
    """(returncode, combined output). Args default to none, so `testpaths` applies.

    STDERR IS FOLDED INTO STDOUT deliberately. pytest writes its summary to
    stdout and its internal errors to stderr, and this function's caller needs to
    parse one text for both; splitting them here would mean a collection error
    that never reached the summary was parsed out of the wrong stream and read as
    "no collection line", which is a true statement about the wrong reason.
    """
    # THROUGH THE SHARED RUNNER, and for this call site that is the whole point:
    # the main invocation passes `-n <jobs>`, so pytest forks xdist workers that
    # inherit the capture pipes. `subprocess.run(capture_output=True, timeout=...)`
    # kills the pytest process on timeout and then blocks in communicate() waiting
    # for a write end the workers still hold -- a gate that hangs instead of
    # refusing. `proc.run` puts the child in its own session and signals the group.
    result = proc.run(
        [pytest_bin, *(args or [])],
        cwd=cwd,
        timeout=RUN_TIMEOUT_S,
    )
    if result.timed_out:
        # A TIMEOUT IS A VERDICT, NOT A TRACEBACK. Until 2026-09-07 this call had a
        # bare `timeout=900` and `main()` no handler, so `TimeoutExpired` propagated
        # out of the gate as an uncaught exception: no verdict, no exit 77, just a
        # stack trace naming subprocess. That was 90 seconds away from happening on
        # its own -- the suite measured 810.16s the same day and grows about 200
        # tests per gate-test port batch.
        #
        # The partial output is RETURNED rather than discarded, because a suite that
        # ran for RUN_TIMEOUT_S and then hung has usually printed the failing test
        # already, and throwing that away leaves the reader with nothing to act on.
        # `proc.run` drains the pipes a SECOND time after the group kill, so the
        # partial text here is whatever the child managed to write before it died.
        partial = result.stdout + result.stderr
        return 1, (
            "%s\ncheck_pytest: the suite did not finish within %ds. That is this "
            "gate refusing, not pytest failing: no verdict was reached, so nothing "
            "here says the tests pass. Re-run on a quiesced tree; if it is genuinely "
            "this slow now, raise RUN_TIMEOUT_S against a measured floor rather than "
            "guessing.\n" % (partial, RUN_TIMEOUT_S)
        )
    return result.returncode, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# THE SELFTEST. A gate that cannot fail is worse than no gate.
# ---------------------------------------------------------------------------


def selftest(pytest_bin: str | None, *, verbose: bool = False) -> bool:
    """Controls in both directions, including one real planted defect.

    Uses the package's own Controls runner rather than a private tally, which is
    the point of having one: the gate that proves the suite runs is itself a
    consumer of the thing the suite tests.
    """
    # FLOOR RAISED WITH THE SUITE, 16 -> 25 -> 29 -> 35 (six corpus-counter
    # controls, then two more for class methods). It was 16 against 19 controls; the
    # parallel-header work adds nine (six string fixtures and three against a real
    # two-worker run), so 19 -> 28. A floor left at 16 would keep passing with the
    # entire parallel block deleted, which is precisely the "the file is not being
    # executed as written" failure the floor exists for. Slack is kept at three,
    # the same margin the previous pair carried.
    c = Controls("check_pytest", floor=44, verbose=verbose)

    # A CORPUS SIZE THAT IS COMFORTABLY ABOVE THE FLOOR, DERIVED FROM IT. These
    # controls used to write 65 as a literal, and raising MIN_TESTS from 40 to 120
    # in phase 3 turned the first one -- the SANITY control, the one that asserts a
    # healthy run is green -- red for a reason that had nothing to do with the
    # thing under test. A literal that must be edited in step with another literal
    # is a second place to forget, so it is computed.
    healthy = MIN_TESTS + 25

    # -- parse_counts, both directions
    real = "collected %d items\n\n============ %d passed in 0.16s ============" % (
        healthy,
        healthy,
    )
    c.check("a real pytest summary parses", parse_counts(real), (healthy, healthy))
    c.check("a crashed run reports no collection", parse_counts("Traceback"), (None, None))
    c.check(
        "a red run parses its collection and its passes separately",
        parse_counts("collected %d items\n1 failed, %d passed in 0.2s" % (healthy, healthy - 1)),
        (healthy, healthy - 1),
    )
    c.check("'collected 1 item' is singular in pytest", parse_counts("collected 1 item")[0], 1)

    # -- the PARALLEL header, both directions. See COLLECTED_RE.
    c.check(
        "THE PARALLEL HEADER: `N workers [M items]` is a collection line too",
        parse_counts("2 workers [%d items]\n%d passed in 41.02s" % (healthy, healthy)),
        (healthy, healthy),
    )
    c.check(
        "'1 worker [1 item]' is singular on both nouns under -n 1",
        parse_counts("1 worker [1 item]")[0],
        1,
    )
    c.check(
        "CONTROL: the SERIAL header still parses, so the union added a form "
        "rather than replacing one",
        parse_counts("collected %d items" % healthy)[0],
        healthy,
    )
    c.check(
        "CONTROL: a run that printed NEITHER header is still refused (this is "
        "the -q shape: xdist prints `bringing up nodes...` and no count at all)",
        parse_counts("bringing up nodes...\nbringing up nodes...\n\n.....")[0],
        None,
    )
    c.check(
        "CONTROL: `created: 2/2 workers` is not a collection line -- it names "
        "processes, not tests, and carries no item count",
        parse_counts("created: 2/2 workers")[0],
        None,
    )
    c.check(
        "CONTROL: the worker form is ANCHORED, so `... 3 workers [7 items]` "
        "inside a failure message yields no count",
        parse_counts("E   AssertionError: expected 3 workers [7 items]")[0],
        None,
    )

    # -- verdict, the whole matrix
    c.check(
        "SANITY: enough collected, all passed, exit 0 is green",
        verdict(corpus=healthy, collected=healthy, passed=healthy, returncode=0),
        "",
    )
    c.truthy(
        "THE FAILURE THIS GATE EXISTS FOR: exit 0 having collected nothing is refused",
        verdict(corpus=healthy, collected=0, passed=None, returncode=0),
    )
    c.truthy(
        "a PARTIAL collection is refused even though pytest exited 0",
        verdict(corpus=healthy, collected=healthy - 20, passed=healthy - 20, returncode=0),
    )
    c.truthy(
        "an empty corpus is refused before its derived floor can be satisfied by 0",
        verdict(corpus=0, collected=0, passed=None, returncode=0),
    )
    c.truthy(
        "a non-zero pytest exit is reported",
        verdict(corpus=healthy, collected=healthy, passed=healthy - 1, returncode=1),
    )
    # A KILLED RUN IS NOT A FAILING TEST, and this gate is the likeliest in the
    # estate to be killed: ~1900s against a 3600s RUN_TIMEOUT_S. Reporting a
    # signal as a plain exit sends the reader hunting a red test that does not
    # exist. Verified ad-hoc when the fix landed; PERSISTED here because an
    # ad-hoc check survives nothing and CI never sees it.
    c.check(
        "a SIGTERMed run says KILLED, not exited",
        "KILLED by signal 15"
        in verdict(corpus=healthy, collected=healthy, passed=healthy, returncode=143),
        True,
    )
    c.check(
        "...and a negative returncode, which is how subprocess spells it",
        "KILLED by signal 9"
        in verdict(corpus=healthy, collected=healthy, passed=healthy, returncode=-9),
        True,
    )
    # THE MIRROR, without which the two above pass for a verdict() that says
    # KILLED unconditionally. 160 is outside the signal band on purpose: treating
    # all of 128+ as signals would swallow real exit codes.
    c.check(
        "CONTROL: an ordinary exit 1 is NOT reported as killed",
        "KILLED" in verdict(corpus=healthy, collected=healthy, passed=healthy, returncode=1),
        False,
    )
    c.check(
        "CONTROL: 160 is outside the signal band",
        "KILLED" in verdict(corpus=healthy, collected=healthy, passed=healthy, returncode=160),
        False,
    )
    c.truthy(
        "exit 0 with fewer passes than collected is refused (a skip is not a pass)",
        verdict(corpus=healthy, collected=healthy, passed=healthy - 1, returncode=0),
    )
    c.truthy(
        "a run with no collection line at all is refused",
        verdict(corpus=healthy, collected=None, passed=None, returncode=2),
    )

    # -- corpus_test_count, both directions
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        (d / "test_fixture.py").write_text(
            'def test_a():\n    pass\n\n\ndef test_b():\n    """def test_not_this()."""\n    pass\n',
            encoding="utf-8",
        )
        c.check("the corpus counts module-level test functions", corpus_test_count(d), 2)
        c.check(
            "CONTROL: a directory with no test files counts zero",
            corpus_test_count(d / "nope"),
            0,
        )
        (d / "helper.py").write_text("def test_ignored():\n    pass\n", encoding="utf-8")
        c.check(
            "CONTROL: a file outside python_files is not counted",
            corpus_test_count(d),
            2,
        )

    # -- THE PLANTED DEFECT, end to end, against the real runner
    if pytest_bin is None:
        c.fail("the planted-defect control needs a pytest binary", "none resolved")
        return c.report()

    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        # Its own pytest.ini pins the rootdir, so this fixture cannot pick up the
        # repo's [tool.pytest.ini_options] by walking upward and cannot be
        # affected by it.
        (d / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        (d / "test_planted.py").write_text(
            "def test_planted_defect():\n"
            "    # Deliberately false. If this passes, the runner is not running.\n"
            "    assert 1 == 2\n",
            encoding="utf-8",
        )
        rc, out = run_pytest(pytest_bin, d, ["-p", "no:cacheprovider", str(d)])
        c.truthy("PLANTED: a false assertion makes the real pytest exit non-zero", rc != 0)
        c.truthy("PLANTED: and the output names the failing test", "test_planted_defect" in out)
        c.truthy(
            "PLANTED: and this gate's verdict refuses it",
            verdict(
                corpus=1, collected=parse_counts(out)[0], passed=parse_counts(out)[1], returncode=rc
            ),
        )

        # CONTROL FOR THE PLANT. Without this, a fixture that was broken for some
        # unrelated reason -- an unwritable tempdir, a pytest that refuses every
        # invocation -- would satisfy every assertion above while proving nothing
        # about the assertion being false.
        (d / "test_planted.py").write_text(
            "def test_planted_defect():\n    assert 1 == 1\n", encoding="utf-8"
        )
        rc, out = run_pytest(pytest_bin, d, ["-p", "no:cacheprovider", str(d)])
        c.check("CONTROL: the same fixture with a TRUE assertion exits 0", rc, 0)
        c.check("CONTROL: ...and collects exactly the one test", parse_counts(out), (1, 1))

        # -- AND THE SAME FIXTURE UNDER -n, AGAINST THE REAL PLUGIN.
        #
        # The six string controls above prove the union matches bytes THIS FILE
        # types. They cannot prove it matches bytes pytest EMITS, and those are
        # the ones the gate reads. An xdist release rewording its header would
        # leave every fixture green and the real gate blind, which is the whole
        # shape this repo keeps paying for. So the header is parsed here out of a
        # genuine two-worker run.
        rc, out = run_pytest(
            pytest_bin,
            d,
            ["-p", "no:cacheprovider", "-n", "2", "--dist", "loadgroup", str(d)],
        )
        if "unrecognized arguments" in out or "no such option" in out:
            # A NAMED REFUSAL, not a mystifying (None, None). Without this the
            # reader sees a parse control fail and goes looking at the regex,
            # which is correct-looking and innocent.
            c.fail(
                "pytest does not understand -n: pytest-xdist is not in this "
                "pytest's environment. Run `bash .ci/bootstrap.sh` (its xdist row "
                "reports ABSENT) rather than editing this control",
                out.strip().splitlines()[-1] if out.strip() else "no output",
            )
        else:
            c.check("PARALLEL: a real -n 2 run of the fixture exits 0", rc, 0)
            c.check(
                "PARALLEL: and THIS MACHINE's xdist header parses to the same "
                "(collected, passed) the serial run gave",
                parse_counts(out),
                (1, 1),
            )
            c.falsy(
                "CONTROL FOR THAT: the -n run printed no serial `collected` line "
                "at all, so it was the worker alternative that matched",
                "collected 1 item" in out,
            )

    # THE CORPUS COUNTER, whose old regex counted a `def test_` written at column
    # 0 INSIDE a string fixture. That inflates the floor `collected >= corpus`, so
    # the failure it produces is a gate red with no defect behind it -- the worst
    # kind, because the next session goes looking for a broken test. Found by
    # writing such a fixture: 2228 counted against 2216 real, 12 phantoms.
    c.check(
        "CORPUS: a real module-level test function is counted",
        count_test_defs("def test_real(gate):\n    pass\n"),
        1,
    )
    c.check(
        "CORPUS: a `def test_` at column 0 INSIDE a string fixture is NOT",
        count_test_defs('SAMPLE = """\ndef test_phantom(gate):\n    pass\n"""\n'),
        0,
    )
    c.check(
        "CORPUS: and a fixture beside a real one leaves exactly the real one",
        count_test_defs(
            'SAMPLE = """\ndef test_phantom(gate):\n    pass\n"""\n\n'
            "def test_real(gate):\n    pass\n"
        ),
        1,
    )
    c.check(
        "CORPUS: a def NESTED inside another function is not counted, because "
        "pytest does not collect one and the floor must not claim it does",
        count_test_defs("def outer():\n    def test_nested():\n        pass\n"),
        0,
    )
    c.check(
        "CORPUS: a method of a Test* class IS counted, because pytest collects it",
        count_test_defs("class TestThing:\n    def test_method(self):\n        pass\n"),
        1,
    )
    c.check(
        "CORPUS: a method of a non-Test class is not, for the same reason",
        count_test_defs("class Helper:\n    def test_method(self):\n        pass\n"),
        0,
    )
    # THE FALLBACK, which is what makes the parse safe to rely on: a file that
    # cannot be parsed is counted exactly as it was before, so this floor still
    # cannot fail for its own reasons.
    c.check(
        "CORPUS: an unparseable file falls back to the regex rather than raising, "
        "so it still counts the one the regex can see",
        count_test_defs("def test_broken(:\n"),
        1,
    )
    c.check(
        "CORPUS: and the fallback still counts what the regex can see in one",
        count_test_defs("def test_seen():\n    pass\ndef test_broken(:\n"),
        2,
    )

    # THE HANG THIS GATE SHIPPED WITH, controlled in both directions. Measured
    # 2026-09-08: `--help` exited 124 after writing ZERO bytes to stdout AND
    # stderr, because it fell through to `resolve_pytest`, whose `timeout=120`
    # did not bound it -- `subprocess.run` killed the child and then blocked in
    # `communicate()` on pipes a GRANDCHILD still held.
    c.check("HANG: --help is recognised", wants_help(["--help"]), True)
    c.check("HANG: and -h too, since a reader will try both", wants_help(["-h"]), True)
    c.check("HANG: an ordinary run is not mistaken for one", wants_help([]), False)
    c.truthy(
        "HANG: and the guard is placed BEFORE resolve_pytest, so --help cannot "
        "fall through into the resolution that hangs",
        help_precedes_resolution(),
    )
    c.truthy("HANG: the usage text names the kill timer", "PYTEST_RUN_TIMEOUT_S" in USAGE)

    # THE KILLER ITSELF, driven against the exact shape that hung: a child whose
    # GRANDCHILD holds the read end open. Killing only the child blocks forever
    # here; `proc.run` kills the GROUP, so it returns. Driven through the shared
    # runner rather than a local copy, because the copy was the first mistake.
    t0 = time.monotonic()
    blocked = proc.run(
        ["bash", "-c", "tail -f /dev/null & echo spawned; tail -f /dev/null"],
        timeout=3,
    )
    elapsed = time.monotonic() - t0
    # THE THRESHOLD IS MEASURED, NOT ROUND. With the group kill: 3.0s and stdout
    # 'spawned'. Without it: 13.1s and stdout EMPTY -- the fallback drain times
    # out and the child's own words are lost. A loose `< 20` passed both, so it
    # proved nothing; 8 separates them and the stdout check below is sharper
    # still, because losing the diagnostic is the part that actually hurts.
    c.truthy(
        "HANG: proc.run bounds a child whose grandchild holds the pipe "
        "(returned in %.1fs; without the group kill this is 13s)" % elapsed,
        elapsed < 8,
    )
    c.truthy(
        "HANG: and the group kill PRESERVES what the child said, which is the "
        "whole point of a diagnostic (stdout is empty without it)",
        "spawned" in blocked.stdout,
    )
    c.check("HANG: and it reports the timeout rather than pretending", blocked.timed_out, True)
    c.check("HANG: its stdout is a string, never None", isinstance(blocked.stdout, str), True)

    return c.report()


def testpath_dirs(root: pathlib.Path) -> list[pathlib.Path]:
    """Every root pytest is configured to collect, read from pyproject.toml.

    THE CORPUS MUST COVER WHAT THE COLLECTION COVERS, or floor 2 stops working.
    This gate used to hard-code `.ci/rediacc_ci/tests` while pytest collected
    whatever `testpaths` listed. The moment a second root was added
    (.claude/rediacc_hooks/tests, 421 tests) the comparison became 615 collected
    against a 187-file corpus, and the rediacc_ci suite could have dropped to zero
    with the sum still comfortably above its floor -- a corpus-derived floor that
    no longer derives from the corpus it is judging.

    Read from the ini rather than restated here, because a second literal list is
    exactly the drift this repo pays for repeatedly.
    """
    with (root / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    listed = cfg.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("testpaths", [])
    return [paths.from_root(*pathlib.PurePosixPath(p).parts, root=root) for p in listed]


USAGE = """\
check:ci-pytest -- run the Python test corpus and refuse a partial pass.

  check_pytest.py              judge the suite
  check_pytest.py --selftest   run this gate's own controls and exit
  check_pytest.py --help       this text

Environment:
  PYTEST_RUN_TIMEOUT_S   kill timer for the suite (default %d seconds, and it
                         must stay BELOW the job's timeout-minutes or it can
                         never fire -- check:ci-inner-timeout-reachable
                         enforces exactly that)
  PYTEST_BIN             pytest to use, ahead of the bootstrap ladder
"""


def wants_help(argv: list[str]) -> bool:
    """Whether the caller asked for usage. A PREDICATE, so it can be controlled.

    The obvious control -- `c.check(main(["--help"]), EXIT_OK)` -- is a trap, and
    it caught me: with the early return planted away, that call falls through and
    runs the ENTIRE suite, so the plant produces a thirty-minute hang instead of a
    red. A control must fail fast or it is not usable as a control.
    """
    return "--help" in argv or "-h" in argv


def help_precedes_resolution() -> bool:
    """The help guard must come BEFORE any resolution, checked structurally.

    This is an ORDERING property, and no run can demonstrate it: a `--help` that
    resolves first still prints usage on a healthy host, and only hangs on the
    broken one. So it is read off the AST rather than driven.
    """
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "main"):
            continue
        guard = next(
            (
                n.lineno
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "wants_help"
            ),
            None,
        )
        resolve = next(
            (
                n.lineno
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "resolve_pytest"
            ),
            None,
        )
        return guard is not None and resolve is not None and guard < resolve
    return False


def main(argv: list[str]) -> int:
    # ANSWERED BEFORE ANY RESOLUTION. `--help` used to fall straight through to
    # `resolve_pytest`, so on a host where the bootstrap hangs, asking this gate
    # how to use it hung too, with no output on either stream. A usage message
    # that depends on a subprocess is not a usage message.
    if wants_help(argv):
        print(USAGE % RUN_TIMEOUT_S)
        return EXIT_OK

    root = paths.repo_root()
    test_dirs = testpath_dirs(root)
    pytest_bin = resolve_pytest(root)

    if "--selftest" in argv:
        if pytest_bin is None:
            return cannot_run("pytest is not available, so the selftest cannot be run either.")
        return EXIT_OK if selftest(pytest_bin, verbose=True) else EXIT_FAIL

    if pytest_bin is None:
        return cannot_run("pytest is not available and the bootstrap did not resolve one.")

    # The controls run BEFORE the real suite is judged, and a control failure
    # refuses to judge it at all. Same order and same reason as
    # check-python-lint.sh: a verdict from an instrument that cannot fail is
    # worse than no verdict.
    if not selftest(pytest_bin):
        print(
            "%s✗ CONTROL FAILED%s: this gate's own controls did not pass, so it refuses\n"
            "  to report on the suite." % (RED, NC),
            file=sys.stderr,
        )
        return EXIT_FAIL

    if not test_dirs:
        print(
            "%s✗%s pyproject.toml lists no `testpaths`, so this gate has no corpus to\n"
            "  measure and pytest has nothing it is required to collect." % (RED, NC),
            file=sys.stderr,
        )
        return EXIT_FAIL

    per_root = [(d, corpus_test_count(d)) for d in test_dirs]
    corpus = sum(n for _, n in per_root)
    for d, n in per_root:
        print("info: %d test function(s) on disk in %s" % (n, paths.relative_to_root(d, root)))
        # A CONFIGURED ROOT THAT HOLDS NOTHING is the shape the sum hides: the other
        # root carries the total past the floor while this one is empty.
        if n == 0:
            print(
                "%s✗%s %s is listed in testpaths and holds no test functions.\n"
                "  Either the suite was deleted or the path is wrong; the summed floor\n"
                "  below cannot see one root collapse."
                % (RED, NC, paths.relative_to_root(d, root)),
                file=sys.stderr,
            )
            return EXIT_FAIL
    print("info: corpus %d across %d root(s) (floor %d)" % (corpus, len(per_root), MIN_TESTS))

    returncode, out = run_pytest(pytest_bin, root, ["-n", str(jobs()), "--dist", "loadgroup"])
    collected, passed = parse_counts(out)
    # pytest exit 4 is a USAGE error: this repo's own ini table is wrong. That is
    # a defect in the tree, not an absent tool, so it is a 1 and never a 77.
    problem = verdict(corpus=corpus, collected=collected, passed=passed, returncode=returncode)
    if problem:
        print(out, file=sys.stderr)
        print("\n%s✗%s %s" % (RED, NC, problem), file=sys.stderr)
        return EXIT_FAIL

    print(
        "%s✓%s %d test(s) collected and passed (corpus %d, floor %d)"
        % (GREEN, NC, collected, corpus, MIN_TESTS)
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
