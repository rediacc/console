"""`devbox_docker` CAN ANSWER TWO WORDS, and every consumer must treat it that way.

Ported from `.ci/scripts/quality/check-devbox-exec.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

The twin's header, carried whole because the incident, the "why static" argument
and the scope limit are each load-bearing:

    WHAT WENT WRONG, measured 2026-08-26:

      .ci/lib/devbox.sh: line 606: sudo docker: command not found

    `devbox_docker` returns plain `docker` when the caller's shell already has
    the docker group, and the TWO-WORD string `sudo docker` when it does not
    (.ci/lib/devbox.sh:58-63). Sixteen call sites relied on word-splitting an
    UNQUOTED $d and were fine. One -- devbox_exec, the function the whole gate
    lane routes through -- wrote `"$d" "${flags[@]}"`, quoting two words as a
    single command name. Every routed gate therefore died on any machine where
    docker needs sudo, which is the default on a fresh Linux host.

    WHY NO EXISTING GATE SAW IT, and why this one is static rather than a runtime
    test. The bug is invisible to every environment CI actually has: runners and
    containers already grant docker without sudo, so the failing branch is never
    taken. A runtime test would have to manufacture a sudo-requiring docker,
    which is neither portable nor honest. But the defect is fully visible in the
    SOURCE -- a quoted expansion where word-splitting is required -- so per
    .claude/skills/testing that routes to a static gate. This is the "could the
    defect be seen without running the product?" question, and the answer is yes.

    B2 exists because fixing B1 surfaced a sibling: devbox_shell was still
    passing the numeric `-u $(id -u):$(id -g)` into the container.
    devbox-entrypoint.sh renumbers `vscode` to the host identity, so the NAME is
    correct on Linux, macOS (501:20, where gid 20 is dialout) and WSL2, while a
    numeric id is correct only where the host's numbering means something inside
    the container. Exec as the wrong identity and git refuses the worktree with
    "dubious ownership", `git ls-files` returns empty, and a gate reports green
    over zero files -- the vacuity failure this whole wave exists to prevent.

    WHAT THIS GATE CANNOT SEE: it reasons about devbox.sh's own call sites. A new
    file elsewhere that shells out to `sudo docker` on its own is out of scope.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`code_of` STRIPS WHOLE-LINE COMMENTS AND THE TWIN SAYS WHY, in a sentence kept at
the function: "Every explanation of the WRONG shape in this repo lives in a
comment, so a scan for that shape must read code only or it fails on its own
documentation. (Learned the hard way by the editorconfig gate, which matched
`binary` inside a PATH.)"

THE REPORTED LINE NUMBERS ARE NUMBERS IN THE FILTERED STREAM, NOT IN THE FILE,
and that is a TWIN DEFECT carried rather than repaired. `code_of "$DEVBOX" |
grep -nE ...` numbers the lines grep actually received, and `code_of` has already
removed every comment line, so a finding reported at line 40 sits somewhere below
line 40 in the real file. Fixing it would change the gate's output and therefore
its differential, so it is reproduced exactly and reported instead.

THE ANTI-VACUITY FLOOR IS 10 CALL SITES and it is the only thing standing between
a collapsed enumeration and a green B1. The twin's wording is carried verbatim
because it names the failure mode rather than the symptom: "B1 SCANNED ALMOST
NOTHING (%d sites) -- the enumeration broke, not the code".

THE FOUR CONTROLS ARE BUILT BY CONCATENATION, never by substituting into a copy
of the real file, and the twin's reason is kept with them: "a substitution
silently yields an identical copy when the targeted line is later reworded, and
the control then passes against unmutated source."

COLOUR IS UNCONDITIONAL IN THE TWIN. It assigns `RED=$'\\033[0;31m'` with no tty
test at all, so its `FAIL` lines carry escape sequences even into a pipe. The
port uses the package logger's decision instead, which is a tty test; the
difference is invisible to the differential because the comparator strips ANSI
before it compares, and it is the better behaviour for a human piping the gate
into a file. Named here so it is a decision rather than a drift.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The subject, repo-relative. This gate reasons about ONE file's call sites; see
# the header for what that deliberately excludes.
DEVBOX_REL = ".ci/lib/devbox.sh"

# The bug shape: a variable holding devbox_docker's answer, expanded QUOTED in
# command position. `"$d" ` / `"${d}" ` at the start of a command.
BUG_RE = re.compile(r'(^|[;&|(]|then |else |do )[ \t]*"\$\{?d\}?"[ \t]')

# Every expansion of that variable in command-ish position, quoted or not. This
# is the anti-vacuity denominator: B1 is a scan, and a scan over nothing passes.
SITE_RE = re.compile(r"\$\{?d\}?[ \t]")

# The numeric-identity shape B2 forbids: `-u "$(id -u)..."`, with or without the
# quote, which is correct only where the host's numbering means something inside
# the container.
NUMERIC_RE = re.compile(r"-u[ \t]+\"?\$\(id -u\)")

# The floor under B1's enumeration. Ten, matching the twin: devbox.sh has carried
# sixteen call sites since the incident, so a count below this means the
# enumeration broke rather than the code being clean.
MIN_SITES = 10


def code_of(text: str) -> str:
    """`grep -vE '^[[:space:]]*#'`: whole-line comments removed.

    Every explanation of the WRONG shape in this repo lives in a comment, so a
    scan for that shape must read code only or it fails on its own
    documentation. (Learned the hard way by the editorconfig gate, which matched
    `binary` inside a PATH.)

    An INLINE comment is left alone, exactly as the twin leaves it: the pattern
    is anchored at a command position, and a trailing `# ...` cannot be one.
    """
    return "\n".join(line for line in text.split("\n") if not re.match(r"^[ \t]*#", line))


def grep_n(pattern: re.Pattern, text: str) -> list[str]:
    """`grep -nE`: `<line-number>:<line>` for every match, numbered from ONE.

    THE NUMBERS ARE POSITIONS IN `text`, which the caller has already stripped of
    comments. See the port notes: that is the twin's behaviour and it is a defect
    carried rather than repaired, because repairing it would change the output
    the differential compares.
    """
    return [
        "%d:%s" % (number, line)
        for number, line in enumerate(text.split("\n"), start=1)
        if pattern.search(line)
    ]


def grep_c(pattern: re.Pattern, text: str) -> int:
    """`grep -cE`: how many LINES match, not how many matches there are."""
    return len([line for line in text.split("\n") if pattern.search(line)])


# ---------------------------------------------------------------------------
# The controls, built by CONCATENATION.
#
# Never by substituting into a copy of the real file: a substitution silently
# yields an identical copy when the targeted line is later reworded, and the
# control then passes against unmutated source.
# ---------------------------------------------------------------------------

CONTROL_BAD = '#!/bin/bash\nd="$(devbox_docker)"\n"$d" exec -u vscode "$cid" bash -lc "$*"\n'

CONTROL_GOOD = (
    "#!/bin/bash\n"
    'd="$(devbox_docker)"\n'
    '$d exec -u vscode "$cid" bash\n'
    'local -a dk; read -r -a dk <<<"$d"\n'
    '"${dk[@]}" exec "$cid" bash\n'
)

CONTROL_NUMERIC = '#!/bin/bash\n$d exec -it -u "$(id -u):$(id -g)" -w "$w" "$cid" bash\n'

CONTROL_COMMENT = (
    '#!/bin/bash\n# $d exec -u "$(id -u)" -- the wrong shape, explained in a comment\n'
)


def main(argv: list[str] | None = None) -> int:
    """Run B1, B2, their anti-vacuity floor and the four controls. 0 clean, 1 otherwise."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    devbox = root / DEVBOX_REL

    fails = 0

    def fail(message: str) -> None:
        nonlocal fails
        print("  FAIL %s" % message)
        fails += 1

    def ok(message: str) -> None:
        print("  ok   %s" % message)

    if not devbox.is_file():
        print("✗ subject under test is missing: %s" % devbox)
        return 1

    code = code_of(devbox.read_text(encoding="utf-8", errors="replace"))

    # --- B1. devbox_docker's answer is never invoked as one quoted word -----
    hits = grep_n(BUG_RE, code)
    if not hits:
        ok("B1. no call site quotes devbox_docker's two-word answer as one command")
    else:
        fail("B1. these invoke a possibly-two-word docker as a single command:")
        for line in hits:
            print("         %s" % line)

    # Anti-vacuity: B1 is a scan, and a scan over nothing passes. Prove the
    # enumeration actually found the call sites it is supposed to be judging.
    sites = grep_c(SITE_RE, code)
    if sites >= MIN_SITES:
        ok("B1 anti-vacuity: %d docker invocation(s) actually scanned" % sites)
    else:
        fail("B1 SCANNED ALMOST NOTHING (%d sites) -- the enumeration broke, not the code" % sites)

    # --- B2. nothing execs into the devbox under a numeric identity ---------
    numeric = grep_n(NUMERIC_RE, code)
    if not numeric:
        ok("B2. container exec uses -u vscode by name, never a numeric id")
    else:
        fail("B2. numeric -u would break on macOS/WSL2 and can yield a vacuous green:")
        for line in numeric:
            print("         %s" % line)

    # --- controls, by CONSTRUCTION -----------------------------------------
    if grep_n(BUG_RE, code_of(CONTROL_BAD)):
        ok("B1 control: a quoted two-word invocation is detected")
    else:
        fail("B1 CONTROL DID NOT FIRE: the planted defect went undetected")

    if grep_n(BUG_RE, code_of(CONTROL_GOOD)):
        fail("B1 IS OVER-BROAD: correct word-splitting and array forms were flagged")
    else:
        ok("B1 control: unquoted and array forms are not flagged")

    if grep_n(NUMERIC_RE, code_of(CONTROL_NUMERIC)):
        ok("B2 control: a numeric container identity is detected")
    else:
        fail("B2 CONTROL DID NOT FIRE: a numeric -u went undetected")

    if grep_n(NUMERIC_RE, code_of(CONTROL_COMMENT)):
        fail("B2 IS OVER-BROAD: prose describing the wrong shape was flagged as code")
    else:
        ok("B2 control: a comment describing the bad shape is not flagged")

    print()
    if fails == 0:
        print("✓ devbox exec: %d docker invocation(s), none mis-quoted." % sites)
        print("  Blind spot: scoped to .ci/lib/devbox.sh's own call sites; a new file")
        print("  that shells out to docker independently is not covered.")
        return 0
    print("✗ devbox exec: %d failure(s)." % fails)
    return 1


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------


def selftest() -> int:
    """Both directions for both detectors, plus the floor and the comment filter.

    The over-broad direction is the one that decides whether this gate survives:
    a B1 that flagged `$d exec` or `"${dk[@]}"` would fail the file it is meant
    to protect, and a gate that is wrong is a gate that gets suppressed.
    """
    ctl = Controls("devbox-exec", floor=20, verbose=True)

    # -- B1, both directions -------------------------------------------------
    ctl.truthy(
        "PLANT: a quoted two-word invocation is detected", grep_n(BUG_RE, code_of(CONTROL_BAD))
    )
    ctl.check(
        "MIRROR: unquoted and array forms are not flagged",
        grep_n(BUG_RE, code_of(CONTROL_GOOD)),
        [],
    )
    ctl.truthy(
        'PLANT: `"${d}" ` with braces is the same defect',
        grep_n(BUG_RE, '"${d}" exec x\n'),
    )
    ctl.truthy(
        "PLANT: the shape is caught after a `then`",
        grep_n(BUG_RE, 'if x; then "$d" exec y; fi\n'),
    )
    ctl.truthy(
        "PLANT: and after a pipe or a semicolon",
        grep_n(BUG_RE, 'a | "$d" exec y\n'),
    )
    ctl.check(
        'MIRROR: `"$d"` as an ARGUMENT rather than a command is not flagged',
        grep_n(BUG_RE, 'echo "$d" here\n'),
        [],
    )
    ctl.check(
        "MIRROR: a comment carrying the defect shape is stripped before the scan",
        grep_n(BUG_RE, code_of('#  "$d" exec -- the wrong shape\n')),
        [],
    )

    # -- B2, both directions -------------------------------------------------
    ctl.truthy(
        "PLANT: a numeric container identity is detected",
        grep_n(NUMERIC_RE, code_of(CONTROL_NUMERIC)),
    )
    ctl.check(
        "MIRROR: a comment describing the bad shape is not flagged",
        grep_n(NUMERIC_RE, code_of(CONTROL_COMMENT)),
        [],
    )
    ctl.check(
        "MIRROR: `-u vscode` by NAME is not flagged",
        grep_n(NUMERIC_RE, '$d exec -u vscode "$cid" bash\n'),
        [],
    )
    ctl.truthy(
        "PLANT: the unquoted numeric form is caught too",
        grep_n(NUMERIC_RE, "$d exec -u $(id -u):$(id -g) x\n"),
    )

    # -- the comment filter, both directions --------------------------------
    ctl.check("a whole-line comment is DROPPED, not blanked", code_of("# gone\nkept\n"), "kept\n")
    ctl.check(
        "an INDENTED whole-line comment is dropped too",
        code_of("   # gone\nkept\n"),
        "kept\n",
    )
    ctl.check("an INLINE comment survives", code_of("kept # tail\n"), "kept # tail\n")

    # -- the numbering, and the defect it carries ---------------------------
    # THE TWIN DEFECT, demonstrated rather than described. The offending line is
    # line 3 of the FILE and is reported as line 1, because `code_of` DROPS the
    # comment lines before `grep -n` ever numbers anything. A reader following
    # the number lands above the finding. Carried, because repairing it would
    # change the gate's output and therefore its differential.
    original = '# a\n# b\n"$d" exec x\n'
    ctl.check(
        "TWIN DEFECT: the number is the position in the COMMENT-STRIPPED stream",
        grep_n(BUG_RE, code_of(original)),
        ['1:"$d" exec x'],
    )
    ctl.check(
        "TWIN DEFECT: and the real position in the FILE is 3, so the number misleads",
        [i for i, line in enumerate(original.split("\n"), start=1) if BUG_RE.search(line)],
        [3],
    )
    ctl.check(
        "grep -c counts LINES, not matches",
        grep_c(SITE_RE, "$d a $d b\n$d c\n"),
        2,
    )

    # -- the whole gate, over fixtures --------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        def run(body: str | None) -> int:
            lib = root / ".ci" / "lib"
            lib.mkdir(parents=True, exist_ok=True)
            target = lib / "devbox.sh"
            if body is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_text(body, encoding="utf-8")
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    os.environ.pop(paths.ROOT_ENV, None)
                else:
                    os.environ[paths.ROOT_ENV] = saved

        clean = "#!/bin/bash\n" + "".join('$d exec -u vscode "$c%d" bash\n' % i for i in range(12))
        ctl.check("MIRROR: a clean devbox.sh with 12 sites passes", run(clean), 0)
        ctl.check("PLANT: one quoted call site reds", run(clean + '"$d" exec x\n'), 1)
        ctl.check(
            "PLANT: a numeric identity reds",
            run(clean + '$d exec -u "$(id -u)" x\n'),
            1,
        )
        ctl.check(
            "PLANT: a devbox.sh with too FEW sites trips the anti-vacuity floor",
            run("#!/bin/bash\n$d exec a\n"),
            1,
        )
        ctl.check("PLANT: a missing subject reds rather than skipping", run(None), 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
