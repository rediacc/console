"""Port of `.ci/scripts/test/gates/test-vacuity-floors.sh`.

Every vacuity floor must actually REFUSE an empty corpus.

WHY THIS IS NOT A `check-*.ts`. `check:ci-enumeration-vacuity` proves a guard is
PRESENT -- a `MIN_*`, the word VACUOUS, an explicit refusal -- and says so in its
own blind-spot line. Presence is a source shape. Whether the floor FIRES is
behaviour. A static version was written on 2026-09-04 and discarded: it was wrong
on all six names it flagged (names inside string literals and comments, an env var
compared by a different script, and one floor wired indirectly as
`needed = observed * MIN_HEADROOM`). No name-matcher can see that last one.
Running the thing can.

WHAT A GREEN HERE DOES NOT COVER, stated so it is not read as more than it is:
only the floors whose corpus is addressable from outside, through an environment
override or a function parameter. The seven whose corpus is fixed relative to
`__dirname`, or which need a built tree or AWS, are confirmed by reading only.

EXIT 77 IS "CANNOT RUN", NOT A VERDICT, and the twin's header records what
conflating the two cost: `.ci/scripts/security/shfmt.sh` exits 77 when it cannot
obtain shfmt at the pin, and in the `quality-security` lane `go install shfmt`
fails. A first version read any non-zero exit as "refused" and then demanded the
word VACUOUS, so CI reported `FAIL: shfmt: refused (exit 77) but never said
VACUOUS` about a floor it never reached. A tool that is absent proves nothing
either way -- and a run where EVERY case skipped has verified nothing, which is
what the exercised-count refusal below is for.

WHERE THE PORT REIMPLEMENTS THE TWIN. The twin greps its captured output with
`grep -qi 'vacuous'`; the port lowercases the combined streams and asks for the
substring. Same predicate, one fewer subprocess, and it reads both streams rather
than a merge decided by the shell.

THE EXERCISED COUNTER IS NOT MODULE STATE, and that is deliberate. The twin
increments `EXERCISED` across a straight-line script; a Python module doing the
same would be shared mutable state across test functions, which under
`-n 8 --dist loadgroup` is exactly the thing that forces an `xdist_group`. Keeping
the four floors and their count inside ONE test function removes the need for the
group instead of declaring one, so this module has NO `xdist_group`: every case is
a subprocess writing only into its own `mkdtemp` directory.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-vacuity-floors.sh"

ROOT = paths.repo_root()
TSX = paths.from_root("node_modules", ".bin", "tsx")

SHFMT = paths.from_root(".ci", "scripts", "security", "shfmt.sh")
RETIRE = paths.from_root(".ci", "scripts", "housekeeping", "retire-shadowed-secrets.py")
SECRET_RENAME = paths.from_root("scripts", "dev", "secret-rename.py")
ACTION_REFS = paths.from_root("scripts", "lib", "action-refs.ts")

# Three of the four need no external tool, so a run in which fewer than three were exercised has verified nothing worth printing a green over.
MIN_EXERCISED = 3

# Load the module by PATH and call the walker directly, so the CLI's usage path -- which exits before the walk -- cannot stand in for the walk itself.
PY_FLOOR = """
import importlib.util, os, sys
path, var, val, func = sys.argv[1:5]
os.environ[var] = val
spec = importlib.util.spec_from_file_location("m", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
getattr(m, func)()
"""


def _says_vacuous(text: str) -> bool:
    return "vacuous" in text.lower()


def _py_floor(script: pathlib.Path, var: str, value: str, func: str) -> harness.RunResult:
    return harness.run(["python3", "-c", PY_FLOOR, str(script), var, value, func], cwd=ROOT)


def test_every_impossible_floor_is_refused_and_says_vacuous(gate):
    """Four floors, one function, because the exercised COUNT is the anti-vacuity
    control for this test itself and must not become module state."""
    gate.log_test("an impossible floor must be refused, in the floor's own words")
    exercised = 0

    # 1. shfmt.sh -- SHFMT_MIN_FILES over the four shell scopes.
    result = harness.run(["bash", str(SHFMT)], cwd=ROOT, env={"SHFMT_MIN_FILES": "999999"})
    if result.rc == 77:
        gate.log_pass("SKIP shfmt: its tool is unavailable here (exit 77); no verdict either way")
    elif result.rc == 0:
        gate.log_fail("shfmt: an impossible floor was ACCEPTED (exit 0); the floor refuses nothing")
    elif not _says_vacuous(result.combined):
        gate.log_fail(
            "shfmt: refused (exit %d) but never said VACUOUS: %s"
            % (result.rc, result.combined[:120])
        )
    else:
        exercised += 1
        gate.assertions += 1
        gate.log_pass("shfmt refuses an impossible floor, and says VACUOUS")

    # 2/3. Two Python floors, driven through their own module.
    for label, script, var in (
        ("retire-shadowed-secrets", RETIRE, "RETIRE_MIN_WORKFLOWS"),
        ("secret-rename", SECRET_RENAME, "SECRET_RENAME_MIN_FILES"),
    ):
        result = _py_floor(script, var, "999999", "files")
        if result.rc == 0:
            gate.log_fail("%s: an impossible %s was accepted" % (label, var))
        if not _says_vacuous(result.combined):
            gate.log_fail("%s: refused but never said VACUOUS: %s" % (label, result.combined[:120]))
        exercised += 1
        gate.assertions += 1
        gate.log_pass("%s refuses an impossible floor, and says VACUOUS" % label)

    # 4. action-refs.ts -- the corpus is a PARAMETER, so the empty case is a real empty tree rather than an impossible threshold. That is the stronger form.
    with harness.temp_dir() as tmp:
        (tmp / ".github" / "workflows").mkdir(parents=True)
        result = harness.run(
            [
                str(TSX),
                "-e",
                "import { collectActionRefs } from './scripts/lib/action-refs.ts';\n"
                "collectActionRefs('%s');" % tmp,
            ],
            cwd=ROOT,
        )
        if result.rc == 0:
            gate.log_fail("action-refs: an EMPTY .github/workflows was accepted")
        if not _says_vacuous(result.combined):
            gate.log_fail("action-refs: refused but never said VACUOUS: %s" % result.combined[:160])
        exercised += 1
        gate.assertions += 1
        gate.log_pass("action-refs refuses an empty .github tree, and says VACUOUS")

    # ANTI-VACUITY FOR THIS TEST ITSELF. Skipping is legitimate per tool; a run
    # where every case skipped has verified nothing and must not print a green.
    if exercised < MIN_EXERCISED:
        gate.log_fail(
            "VACUOUS: only %d floor(s) were actually exercised, floor %d"
            % (exercised, MIN_EXERCISED)
        )
    gate.assertions += 1
    gate.log_pass("%d floor(s) exercised (skips are named above)" % exercised)


def test_shfmt_accepts_the_real_corpus(gate):
    """The other half: a floor that always fires is as useless as one that never does."""
    gate.log_test("CONTROL: the REAL corpus must still pass")
    result = harness.run(["bash", str(SHFMT)], cwd=ROOT)
    if result.rc == 77:
        gate.log_pass("SKIP CONTROL shfmt: its tool is unavailable here (exit 77)")
        return
    if result.rc != 0:
        gate.log_fail(
            "shfmt: the REAL corpus was refused; the floor is above the true count: %s"
            % result.combined[:200]
        )
    gate.assertions += 1
    gate.log_pass("CONTROL: shfmt accepts the real corpus")


def test_action_refs_accepts_the_real_corpus(gate):
    gate.log_test("CONTROL: action-refs over the real tree")
    result = harness.run(
        [
            str(TSX),
            "-e",
            "import { collectActionRefs } from './scripts/lib/action-refs.ts';\n"
            "collectActionRefs('%s');" % ROOT,
        ],
        cwd=ROOT,
    )
    if result.rc != 0:
        gate.log_fail(
            "action-refs: the REAL corpus was refused; the floor is above the true count: %s"
            % result.combined[:200]
        )
    gate.assertions += 1
    gate.log_pass("CONTROL: action-refs accepts the real corpus")


def test_the_four_subjects_are_all_present(gate):
    """PORT-ONLY, and it is the refusal the twin cannot make cheaply. Every case
    above runs a script BY PATH. A path that no longer exists produces a non-zero
    exit and no VACUOUS text, which the twin reports as `refused but never said
    VACUOUS` -- a message about wording for a file that is not there. Probing
    first names the missing subject instead."""
    gate.log_test("each floor's subject is where this module drives it")
    missing = [
        paths.relative_to_root(p)
        for p in (SHFMT, RETIRE, SECRET_RENAME, ACTION_REFS)
        if not p.is_file()
    ]
    if missing:
        gate.log_fail(
            "these floor subjects are missing, so their cases could not have run: %s"
            % ", ".join(missing)
        )
    if not TSX.is_file():
        gate.log_fail(
            "node_modules/.bin/tsx is absent, so the action-refs floor could not run at "
            "all -- which is a FAILURE and not a pass. Fix: npm install && "
            "npm run install:natives"
        )
    gate.assertions += 1
    gate.log_pass("all 4 floor subjects and tsx are present")
