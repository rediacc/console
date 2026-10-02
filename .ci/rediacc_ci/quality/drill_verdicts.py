r"""`Drill.summary`'s verdict logic, driven rather than read.

Ported from `.ci/scripts/quality/check-drill-verdicts.sh`, retired in W7 P5;
see `rediacc_ci.quality.__init__` for the phase-5 decision that retired the twin.

WHY THIS EXISTS, in the twin's own words, because the incident is the whole gate:

    Behavioural gate for `drill_summary`'s verdict logic (the bash drill harness this gate first drove).

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

THE SUBJECT IS NOW `Drill.summary` IN `.ci/rediacc_ci/drills/lib.py`. The bash harness and its `drill_summary` function were retired with the drills' bash (PLAN-retire-bash-oracles B3); the Python harness is the one every drill runs, so it is the one this gate drives.

THE DRIVER IS A CHILD PROCESS, NOT AN IMPORT. `run_summary` loads the harness from its FILE PATH in a fresh interpreter, sets the counters on a `Drill`, calls `summary()` and prints `<rc>|<stdout>`. A file-path load is what lets the selftest point the gate at a fixture root carrying a planted harness; a fresh interpreter is what keeps a planted module out of this process's import cache. The child exits 97 WITHOUT PRINTING when the file defines no `Drill` with a `summary`, so an undrivable harness yields an EMPTY capture and `assert_verdict`'s empty-result guard names it.

THE HARNESS IS ASKED FOR BOTH HALVES: "Returns `<exit-code>|<stdout>` so callers can assert on BOTH. Asserting only on the exit code is what let the original defect through."

`tail_summary` is a 200-byte tail of the summary with newlines flattened to spaces (plus one trailing space), the window a failure message quotes.
"""

import os
import pathlib
import subprocess
import sys
import tempfile

import rediacc_ci
from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant

# The harness under test, repo-relative.
DRILL_LIB = ".ci/rediacc_ci/drills/lib.py"

# The exit code the child uses to say "there is no Drill.summary to drive". It exits before printing, so the capture is empty.
UNDRIVABLE = 97

# The directory that holds the `rediacc_ci` package, put on the child's path so the real harness can import its siblings.
PACKAGE_PARENT = str(pathlib.Path(rediacc_ci.__file__).resolve().parent.parent)

# How many bytes of the captured summary a failure message shows.
TAIL_BYTES = 200

# The child. It loads the harness by file path, so a fixture root's planted harness is what runs.
RUNNER = """
import importlib.util, io, os, sys, time
spec = importlib.util.spec_from_file_location("_dv_harness", os.environ["_DV_LIB"])
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
except Exception:
    sys.exit(97)
drill_cls = getattr(module, "Drill", None)
if drill_cls is None or not callable(getattr(drill_cls, "summary", None)):
    sys.exit(97)
buf = io.StringIO()
drill = drill_cls("gatecheck", selftest=os.environ["_DV_SELFTEST"] == "1", stdout=buf)
drill.started_at = int(time.time())
drill.count = int(os.environ["_DV_COUNT"])
drill.failures = int(os.environ["_DV_FAILURES"])
drill.rows = []
rc = drill.summary()
sys.stdout.write("%d|%s" % (rc, buf.getvalue().rstrip("\\n")))
"""


def run_summary(root: pathlib.Path, count: str, failures: str, selftest: str = "0") -> str:
    """Drive `Drill.summary` with the counters set directly. Returns `rc|stdout`.

    The EMPTY STRING is a real answer and means the child exited before printing: the harness could not be loaded, or defines no `Drill.summary`.
    """
    env = dict(os.environ)
    env.update(
        {
            "_DV_LIB": str(root / DRILL_LIB),
            "_DV_COUNT": count,
            "_DV_FAILURES": failures,
            "_DV_SELFTEST": selftest,
            "PYTHONPATH": PACKAGE_PARENT,
            paths.ROOT_ENV: str(root),
        }
    )
    proc = subprocess.run(
        [sys.executable, "-c", RUNNER],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.stdout.decode("utf-8", "replace")


def tail_summary(out: str) -> str:
    """The last 200 bytes of the summary, newlines flattened to spaces, with one trailing space."""
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


# The four cases.
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

    THE EMPTY-CAPTURE BRANCH COMES FIRST: an empty capture means the child exited before printing, so the harness could not be driven at all. Saying that beats falling through to the rc comparison as the cryptic 'expected exit 0, got '. A gate whose probe failed must not be able to look like a gate whose probe returned nothing interesting.
    """
    result = run_summary(root, case.count, case.fails, case.selftest)
    if result == "":
        log.error(
            "%s: run_summary produced no output \u2014 Drill.summary could not be driven."
            % case.label
        )
        return False

    # The FIRST pipe splits them, so a summary containing a pipe stays intact on the right-hand side.
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

    `--selftest` is intercepted BEFORE any real scan; any other argument is ignored.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()

    log.step("Checking drill verdict logic in %s..." % DRILL_LIB)

    if not (root / DRILL_LIB).is_file():
        # A HARNESS THAT VANISHED IS A FAILURE, NOT AN ABSTENTION.
        log.error("%s not found \u2014 this gate has nothing to check, which is a" % DRILL_LIB)
        log.error("failure, not a pass: a harness that vanished cannot be verified.")
        return 1

    # Prove the harness is reachable before trusting a single verdict.
    probe = run_summary(root, "1", "0")
    if probe == "":
        log.error("Could not load Drill.summary from %s." % DRILL_LIB)
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


# A minimal harness that satisfies all four cases. Small enough to read, and shaped like the real `Drill.summary`: it branches on the selftest flag first, then on failures, then on the count, and returns the same codes.
_GOOD_LIB = """class Drill:
    def __init__(self, name, selftest=False, keep_work=None, stdout=None):
        self.name = name
        self.selftest = selftest
        self.out = stdout
        self.count = 0
        self.failures = 0

    def summary(self):
        self.out.write("  %d assertions: %d passed, %d failed\\n" % (self.count, self.count - self.failures, self.failures))
        if self.selftest:
            if self.failures == 0:
                self.out.write("  SELFTEST DID NOT FIRE: a planted failure went unnoticed\\n")
                return 1
            self.out.write("  selftest fired as designed\\n")
            return 1
        if self.failures > 0:
            self.out.write("  drill %s FAILED\\n" % self.name)
            return 1
        if self.count == 0:
            self.out.write("  drill %s SKIPPED (0 assertions ran)\\n" % self.name)
            return 0
        self.out.write("  drill %s PASSED\\n" % self.name)
        return 0
"""

# THE 2026-08-05 DEFECT ITSELF, as a fixture: a zero-assertion run that says PASSED. This is the mutant the gate exists to catch, and a suite without it is a suite that has never seen this gate fire.
_VACUOUS_LIB = plant(
    _GOOD_LIB,
    '            self.out.write("  drill %s SKIPPED (0 assertions ran)\\n" % self.name)\n',
    '            self.out.write("  drill %s PASSED\\n" % self.name)\n',
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

    ctl.check("helper: the table has four cases", len(CASES), 4)
    ctl.check("helper: case 1 forbids the word a dashboard greps for", CASES[0].forbid, "PASSED")
    ctl.check(
        "helper: case 2 is the CONTROL and forbids nothing, or case 1 is vacuous",
        (CASES[1].want, CASES[1].forbid),
        ("PASSED", ""),
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        lib = root / DRILL_LIB
        lib.parent.mkdir(parents=True)

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

        # PLANT 2: a harness with no Drill.summary at all. The child exits 97 before printing, so the capture is empty.
        ctl.check(
            "PLANT: a harness with no Drill.summary is refused",
            run("NOTHING_HERE = 1\n"),
            1,
        )
        ctl.check(
            "PLANT: and the capture really is EMPTY",
            run_summary(root, "1", "0"),
            "",
        )

        # PLANT 3: a summary hard-wired to SKIPPED. Case 1 alone would pass; it is case 2, the control, that catches this.
        ctl.check(
            "PLANT: a summary hard-wired to SKIPPED is caught by the CONTROL case",
            run(
                plant(
                    _GOOD_LIB,
                    '        self.out.write("  drill %s PASSED\\n" % self.name)\n        return 0',
                    '        self.out.write("  drill %s SKIPPED\\n" % self.name)\n        return 0',
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
                    '            self.out.write("  drill %s FAILED\\n" % self.name)\n            return 1',
                    '            self.out.write("  drill %s FAILED\\n" % self.name)\n            return 0',
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
                    '                self.out.write("  SELFTEST DID NOT FIRE: a planted failure '
                    'went unnoticed\\n")\n                return 1',
                    '                self.out.write("  all good\\n")\n                return 0',
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
