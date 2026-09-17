"""A SHELL FILE CAN GROW UNTIL IT KILLS THE LINTER, and nothing noticed.

Ported from `.ci/scripts/quality/check-shell-size.sh`, which is NOT deleted; see
`rediacc_ci.quality.__init__` for why both copies live until a committed
differential ledger retires the twin.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED ACROSS. The measurements below are the original's.
-----------------------------------------------------------------------------

WHAT WENT WRONG, measured 2026-08-25: a shellcheck 0.10.0 run over 453 files
was OOM-KILLED. Batching did not help, because the cause was ONE file --
.claude/hooks/stop/test-worklist-v5.sh at 11,955 lines -- whose dataflow
analysis took 2714 MB on its own. With `extended-analysis=false` the same file
took 199 MB. The fix was to split it into a 135-line runner plus 22 topic
files, which also took the path-scan gate from 51m02s to 7.9s.

NOTHING PREVENTS IT COMING BACK. Every content-based linter passed that file:
its own shellcheck findings were clean, shfmt was clean, and the size was
invisible to all of them by construction -- a linter cannot report a file it
died on. That is the i18n lesson exactly: fixed by hand, ungated.

THE RULE IS SIZE **OR** THE DIRECTIVE, not size alone. A genuinely large
generated or table-driven script is legitimate; what is not legitimate is one
that is both large AND asks shellcheck for the expensive analysis. Carrying
`# shellcheck extended-analysis=false` is an explicit, reviewable statement
that the author knows the file is big, so the gate accepts it.

WHY THIS THRESHOLD. It was set against a measured maximum, and that maximum has
MOVED TWICE since, in opposite directions, which is why this paragraph no longer
names a file or a number. It used to read "the largest shell file is run.sh at
2,418 lines": run.sh is now 120 lines (the 2026-09-06 router split moved its body
to .ci/legacy/run-legacy.sh), and the real maximum today is LARGER than the figure
that sentence offered as the historic peak. A threshold justified by a specific
file's size is a comment that goes wrong every time that file changes, and goes
wrong silently because nothing re-derives it.

What is durable: 5,000 sits far above anything this tree has held and far below
the 11,955 that actually caused the OOM, so it fires long before the failure it
exists to prevent. To re-derive the current maximum:

    git ls-files '*.sh' | xargs wc -l | sort -n | tail -3

WHAT THIS GATE CANNOT SEE: lines are a proxy. A 3,000-line file of pathological
nesting could still be expensive, and a 6,000-line file of flat `case` arms is
cheap. The proxy is deliberate -- it is mechanical, has no false negatives in
the direction that hurt us, and the directive is the documented escape.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE COLOURS ARE UNCONDITIONAL IN THE TWIN, and that is worth stating because
every other gate in this batch tests `[ -t 1 ]` first. `check-shell-size.sh`
assigns `RED=$'\\033[0;31m'` with no tty test at all, so it writes escape bytes
into a CI log and into a pipe. That is arguably a defect; it is NOT fixed here,
because fixing it would change the bytes and the port's job is to keep the
verdict. `scripts/lib/shadow-gate.ts` strips ANSI before comparing, so the two
sides agree either way, and a reader diffing the raw streams sees the same file.

EVERYTHING GOES TO STDOUT. `fail()` in the twin is `echo "  ${RED}FAIL${NC} $*"`
with no `>&2`, and so are the offender list, the two advice lines and the final
verdict. This gate never writes to stderr at all. `rediacc_ci.log` would put
messages on stderr, which is the house rule and the WRONG answer here, so
nothing in this module uses it.

`FAIL` IS FOLLOWED BY ONE SPACE, NOT TWO, and that has a consequence the next
reader should not have to rediscover: `shadow-gate.ts`'s marker table carries
`/^FAIL\\s\\s+/` (the `gate-controls.sh` tally shape), so these lines are NOT
recognised as findings by default and the differential for this pair is recorded
with an explicit `--finding-re`. The alternative -- widening the marker to one
space -- would reclassify unrelated prose across the whole estate.

`read -r n < <(wc -l <"$f")` IS AN UNREADABLE-FILE PROBE, not a line count with
extra steps. The twin's comment records that this was once `|| echo 0`, which
"gave an unreadable file the same value as an empty one -- so a permission error
or a broken symlink passed the size check silently. That is the exact vacuity
this gate exists to prevent, sitting inside the gate itself. Caught by
check-swallowed-failures." The port keeps the three-valued answer: a count, the
string UNREADABLE, or the empty string for "under the limit".

The twin also explains why it uses `read` rather than `${n//[[:space:]]/}`:
"check-control-vacuity counts ANY `${VAR//x/y}` in a gate as control-building,
so a substitution used for data cleaning reads as a control that never proves
its plant landed." That constraint is about BASH source text and does not
survive into Python, so it is recorded here as history rather than obeyed.

`wc -l` COUNTS NEWLINES, NOT LINES. A file whose last line has no terminator is
reported one short by `wc` and must be reported one short here, or a file
sitting exactly on the threshold would flip verdicts between the two sides.
`text.count("\\n")` is the faithful spelling; `len(splitlines())` is not.

DISCOVERED, TRACKED AND UNTRACKED. `git ls-files` alone is blind to a script not
yet committed, which is exactly when a file is being grown, so the twin unions
`ls-files '*.sh'` with `ls-files --others --exclude-standard '*.sh'` and pipes
the result through `sort -u`. Under `LC_ALL=C` -- which the differential harness
pins and CI sets -- that sort is byte order, which is what Python's own `sorted`
on `str` gives for these ASCII paths.

`gen_lines` IS NOT `seq`. The twin says why: "ubuntu-slim does not ship it, and
check-ci-compat flags it. Same reason mapfile is avoided below." Neither
constraint applies to a Python range, and both are recorded here because the
next person to touch the bash will need them.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The escapes, assigned unconditionally exactly as the twin assigns them. See the port notes: this is deliberate fidelity, not an oversight.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# The threshold, overridable by the same environment variable the twin reads. Read at CALL time rather than at import, so a test can point one run at a small limit without the module having been imported under the other value.
MAX_LINES_ENV = "SHELL_MAX_LINES"
DEFAULT_MAX_LINES = 5000

# The anti-vacuity floor. A scan over nothing passes, so a scan over nothing is a FAILURE. 50 is far below the ~450 shell files this tree carries and far above anything a collapsed glob would return.
MIN_FILES = 50

# The sentinel `over_limit` returns for a file it could not read. A distinct value rather than a number, because "I could not look" and "it is 0 lines long" are different claims and collapsing them is the defect this gate polices.
UNREADABLE = "UNREADABLE"

# The escape hatch, as a real directive line rather than prose mentioning it. This gate's own header names the flag several times, which is exactly why the pattern demands `#`, then optional space, then the literal word `shellcheck`.
DIRECTIVE_RE = r"^[[:space:]]*#[[:space:]]*shellcheck[[:space:]]+.*extended-analysis=false"


def max_lines(env: dict[str, str] | None = None) -> int:
    """`$SHELL_MAX_LINES`, or 5000. Never raises on a non-numeric value.

    The twin does not validate it either: `[[ "$n" -le "$MAX_LINES" ]]` with a
    non-numeric MAX_LINES is a bash arithmetic error that aborts the comparison,
    which is louder than what happens here. Nothing sets the variable to
    anything but a number today, and a port is not the place to invent a new
    failure mode, so a bad value falls back to the default.
    """
    raw = (os.environ if env is None else env).get(MAX_LINES_ENV, "")
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_MAX_LINES


def has_directive(text: str) -> bool:
    """Is there a real `# shellcheck ... extended-analysis=false` LINE?

    The distinction is the whole rule: this gate's own documentation says the
    words several times, and a file is allowed to be large only when it DECLARES
    the flag. Written out with the POSIX classes spelled as their Python
    equivalents rather than as `\\s`, for the reason `rediacc_ci.quality.npmrc`
    records at length: POSIX space is exactly [ \\t\\n\\v\\f\\r], while Python's
    `\\s` on a str pattern also matches U+00A0 and friends.
    """
    pattern = re.compile(
        r"^[ \t\n\v\f\r]*#[ \t\n\v\f\r]*shellcheck[ \t\n\v\f\r]+.*extended-analysis=false"
    )
    return any(pattern.search(line) for line in text.split("\n"))


def over_limit(path: pathlib.Path, limit: int) -> str:
    """The line count when the file breaks the rule, UNREADABLE, or "".

    Three-valued on purpose; see the port notes. "" means either "small enough"
    or "large but declared", which the twin also collapses, because the caller
    treats both as compliant and printing them differently would be a different
    gate.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # A FILE THE GATE CANNOT READ MUST NOT READ AS COMPLIANT. A permission error, a broken symlink, a path that vanished between enumeration and here -- all of them arrive as OSError and all of them mean the same thing: this file was not checked.
        return UNREADABLE
    count = text.count("\n")
    if count <= limit:
        return ""
    if has_directive(text):
        return ""
    return str(count)


def discover(root: pathlib.Path) -> list[str]:
    """Every `*.sh` git knows about, tracked AND untracked, sorted and unique.

    Returns paths RELATIVE to the root, which is what the twin's array holds and
    what its offender lines print. A failed `git` is not distinguished from an
    empty repository here, exactly as the twin's `2>/dev/null` does not
    distinguish them -- and it does not need to, because the MIN_FILES floor
    below turns both into a loud failure rather than a clean pass. That is the
    difference between swallowing a failure and having a net under it.
    """
    out: set[str] = set()
    for args in (
        ["ls-files", "*.sh"],
        ["ls-files", "--others", "--exclude-standard", "*.sh"],
    ):
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        for line in proc.stdout.split("\n"):
            if line != "":
                out.add(line)
    return sorted(out)


def gen_lines(count: int) -> str:
    """`count` trivial shell lines, built rather than copied.

    The controls are generated with this and never by mutating a real file: a
    substitution can silently no-op, and the control then passes against
    unmutated input. That is the `check-control-vacuity.sh` rule, and it is the
    reason this function exists at all instead of the fixtures being sampled
    from the tree.
    """
    return "".join("echo %d\n" % i for i in range(1, count + 1))


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 failure. Every line goes to STDOUT."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    limit = max_lines()
    fails = 0

    def ok(message: str) -> None:
        print("  ok   %s" % message)

    def bad(message: str) -> None:
        nonlocal fails
        print("  %sFAIL%s %s" % (RED, NC, message))
        fails += 1

    files = discover(root)
    scanned = 0
    offenders: list[str] = []
    for rel in files:
        target = root / rel
        if rel == "" or not target.is_file():
            continue
        scanned += 1
        verdict = over_limit(target, limit)
        if verdict == UNREADABLE:
            offenders.append(
                "%s (could not be read -- reporting rather than assuming compliant)" % rel
            )
        elif verdict != "":
            offenders.append("%s (%s lines)" % (rel, verdict))

    # --- S1. no shell file is both oversized and asking for the expensive pass
    if not offenders:
        ok("S1. no shell file exceeds %d lines without the directive" % limit)
    else:
        bad("S1. these will make shellcheck's dataflow analysis explode:")
        for entry in offenders:
            print("         %s" % entry)
        print("         Fix by splitting the file, or add this line if the size is deliberate:")
        print("         # shellcheck extended-analysis=false")

    # --- S2. anti-vacuity: a scan over nothing passes -----------------------
    if scanned >= MIN_FILES:
        ok("S2. %d shell file(s) actually scanned" % scanned)
    else:
        bad("S2. SCANNED ONLY %d FILE(S) -- the enumeration broke, not the tree" % scanned)

    # --- controls, by CONSTRUCTION ------------------------------------------ Generated with a range, never by copying and mutating a real file: a substitution can silently no-op, and the control then passes against unmutated input.
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)

        big = tmpdir / "big.sh"
        big.write_text(gen_lines(limit + 10), encoding="utf-8")
        if over_limit(big, limit) != "":
            ok("control: an oversized file with no directive is detected")
        else:
            bad("CONTROL DID NOT FIRE: an oversized file went undetected")

        big_ok = tmpdir / "big-ok.sh"
        big_ok.write_text(
            "#!/bin/bash\n# shellcheck extended-analysis=false\n" + gen_lines(limit + 10),
            encoding="utf-8",
        )
        if over_limit(big_ok, limit) != "":
            bad("IS OVER-BROAD: a file that declared the directive was still flagged")
        else:
            ok("control: an oversized file carrying the directive is allowed")

        small = tmpdir / "small.sh"
        small.write_text(gen_lines(10), encoding="utf-8")
        if over_limit(small, limit) != "":
            bad("IS OVER-BROAD: a small file was flagged")
        else:
            ok("control: a small file is not flagged")

        prose = tmpdir / "prose.sh"
        prose.write_text(
            "#!/bin/bash\n# we could add extended-analysis=false here, but we have not\n"
            + gen_lines(limit + 10),
            encoding="utf-8",
        )
        if over_limit(prose, limit) != "":
            ok("control: prose mentioning the directive does not count as declaring it")
        else:
            bad("CONTROL DID NOT FIRE: a comment about the flag was accepted as the flag")

    print()
    if fails == 0:
        print(
            "%s✓%s shell size: %d file(s), none over %d lines undeclared."
            % (GREEN, NC, scanned, limit)
        )
        print("  Blind spot: lines are a PROXY for analysis cost. Pathological nesting in a")
        print("  small file is still expensive, and a long flat file is still cheap.")
        return 0
    print("%s✗%s shell size: %d failure(s)." % (RED, NC, fails))
    return 1


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. The twin already carries four inline
    controls over `over_limit`, and those are preserved above, byte for byte, on
    every real run. What it has no way to exercise is the ENUMERATION and the
    two assertions built on it, because they read the real tree. Those are what
    this adds, over throwaway git repositories.
    """
    ctl = Controls("shell-size", floor=17, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)

        # -- over_limit, the decision function, driven directly -------------
        small = tmpdir / "s.sh"
        small.write_text(gen_lines(5), encoding="utf-8")
        ctl.check("CONTROL: a small file is not flagged", over_limit(small, 20), "")

        big = tmpdir / "b.sh"
        big.write_text(gen_lines(30), encoding="utf-8")
        ctl.check("PLANT: an oversized file is flagged with its count", over_limit(big, 20), "30")

        declared = tmpdir / "d.sh"
        declared.write_text(
            "#!/bin/bash\n# shellcheck extended-analysis=false\n" + gen_lines(30),
            encoding="utf-8",
        )
        ctl.check("MIRROR: the directive excuses the size", over_limit(declared, 20), "")

        indented = tmpdir / "i.sh"
        indented.write_text(
            "#!/bin/bash\n    #  shellcheck  shell=bash extended-analysis=false\n" + gen_lines(30),
            encoding="utf-8",
        )
        ctl.check(
            "MIRROR: an indented directive with extra flags still counts",
            over_limit(indented, 20),
            "",
        )

        prose = tmpdir / "p.sh"
        prose.write_text(
            "# we could add extended-analysis=false here, but we have not\n" + gen_lines(30),
            encoding="utf-8",
        )
        ctl.check("PLANT: prose mentioning the flag is not the flag", over_limit(prose, 20), "31")

        # THE BOUNDARY, both sides of it. `<=` is the twin's comparison, so a
        # file exactly ON the limit is compliant and one line more is not.
        exact = tmpdir / "e.sh"
        exact.write_text(gen_lines(20), encoding="utf-8")
        ctl.check("BOUNDARY: exactly the limit is compliant", over_limit(exact, 20), "")
        over = tmpdir / "o.sh"
        over.write_text(gen_lines(21), encoding="utf-8")
        ctl.check("BOUNDARY: one line over the limit is not", over_limit(over, 20), "21")

        # NO TRAILING NEWLINE. `wc -l` counts terminators, so 21 lines without a final newline is 20 to this gate. A port using splitlines() would disagree with its twin here and nowhere else.
        noeol = tmpdir / "n.sh"
        noeol.write_text(gen_lines(20) + "echo 21", encoding="utf-8")
        ctl.check("BOUNDARY: a missing final newline is not a line", over_limit(noeol, 20), "")

        # THE UNREADABLE CASE, which is the vacuity this gate polices inside itself. Skipped rather than faked when the process can read anything regardless of mode, which is what running as uid 0 means.
        locked = tmpdir / "locked.sh"
        locked.write_text(gen_lines(30), encoding="utf-8")
        locked.chmod(0o000)
        if os.geteuid() == 0:
            ctl.check(
                "VACUITY: skipped, uid 0 can read a 000 file so the probe proves nothing",
                True,
                True,
            )
        else:
            ctl.check(
                "VACUITY: an unreadable file reports UNREADABLE, never compliant",
                over_limit(locked, 20),
                UNREADABLE,
            )
        locked.chmod(0o644)

        ctl.check(
            "VACUITY: a path that does not exist reports UNREADABLE",
            over_limit(tmpdir / "gone.sh", 20),
            UNREADABLE,
        )

        # -- has_directive, both directions ---------------------------------
        ctl.truthy(
            "CONTROL: a bare directive line is recognised",
            has_directive("# shellcheck extended-analysis=false\n"),
        )
        ctl.falsy(
            "MIRROR: the words without the `shellcheck` token are not a directive",
            has_directive("# extended-analysis=false\n"),
        )
        ctl.falsy(
            "MIRROR: a directive without the flag is not this directive",
            has_directive("# shellcheck disable=SC2086\n"),
        )
        ctl.falsy("MIRROR: an empty file declares nothing", has_directive(""))

    # -- the whole gate, over throwaway repositories -------------------------
    def build(tmp: str, *, fillers: int, oversized: int, limit: int) -> pathlib.Path:
        root = pathlib.Path(tmp)
        for i in range(fillers):
            (root / ("filler%02d.sh" % i)).write_text("echo hi\n", encoding="utf-8")
        for i in range(oversized):
            (root / ("huge%02d.sh" % i)).write_text(gen_lines(limit + 5), encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
        return root

    def run(root: pathlib.Path, limit: int) -> int:
        saved_root = os.environ.get(paths.ROOT_ENV)
        saved_max = os.environ.get(MAX_LINES_ENV)
        os.environ[paths.ROOT_ENV] = str(root)
        os.environ[MAX_LINES_ENV] = str(limit)
        try:
            return main([])
        finally:
            for name, value in ((paths.ROOT_ENV, saved_root), (MAX_LINES_ENV, saved_max)):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    with tempfile.TemporaryDirectory() as tmp:
        ctl.check(
            "CONTROL: a tree of small files above the floor passes",
            run(build(tmp, fillers=MIN_FILES + 2, oversized=0, limit=20), 20),
            0,
        )
    with tempfile.TemporaryDirectory() as tmp:
        ctl.check(
            "PLANT: one oversized file reds the whole gate",
            run(build(tmp, fillers=MIN_FILES + 2, oversized=1, limit=20), 20),
            1,
        )
    with tempfile.TemporaryDirectory() as tmp:
        # THE ANTI-VACUITY CASE, and it is the one that matters most: a tree the enumeration cannot see reads exactly like a clean tree unless S2 fires.
        ctl.check(
            "VACUITY: a tree below the file floor is a FAILURE, not a pass",
            run(build(tmp, fillers=3, oversized=0, limit=20), 20),
            1,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
