"""Under `pipefail`, a locally-defined function piped into `grep -q` is a RACE.

Ported from `.ci/scripts/quality/check-pipefail-grep-q.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live until a differential
ledger row exists over K distinct trees. Its gate header registers it as step
"No racing pipefail/grep -q detectors", lane quality-code, emit false, and it
carries this BLOCKER, which is about WIRING rather than about the defect class,
so it stays with the bash file: "runs before this lane's `- id: setup` step, so
its hand-written step carries no `steps.setup.outcome` guard. Emitting it into
the region would move it below that guard and skip it whenever setup fails."

The twin's `why:` line, which is the one-sentence version: "A detector built as
`producer | grep -q` under pipefail cannot reliably fail: grep -q exits at its
first match, SIGPIPEs the producer, and pipefail makes that 141 the verdict.
check-ci-watch-recipe.sh shipped exactly that in both detectors and certified 124
files clean over a real offender for as long as it existed."

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED WHOLE. Every paragraph below is evidence that cannot
be recovered from the code, and a port that summarised it would destroy the only
copy.
-----------------------------------------------------------------------------

THE MECHANISM. `grep -q` exits the instant it matches. That closes the pipe, the
producer gets SIGPIPE, and its status becomes 141. `set -o pipefail` makes the
RIGHTMOST NON-ZERO status the pipeline's status -- so a pipeline that MATCHED
reports 141, i.e. false. Whether it happens depends on whether the producer has
already written everything into the 64 KB pipe buffer and exited, which is a
function of output size and machine load. The same code returns different answers
on different days.

WHAT IT COST. `.ci/scripts/quality/check-ci-watch-recipe.sh` had exactly this in
both of its detectors:

    hands_out_banned() { advice_only "$1" | grep -qE '<banned>'; }

Measured 2026-08-27 against .claude/hooks/test-hooks.sh, 1,644 lines then (hit at
line 692 of the filtered stream): 8/8 trips WITHOUT pipefail, 0/8 WITH it. The gate had
been printing "no hand-rolled watch in 124 scanned file(s)" over a real offender,
and went red exactly once -- under `npm run ci`'s parallel load, where the timing
flipped. Its own four controls could not have caught it: all of them ran on
2-line fixtures, where the producer finishes long before `grep -q` exits, so the
mechanism does not exist at that size.

THE SUBJECT IS THE SIZE, NOT THAT FILE. It was 1,644 lines the day this was
measured, 2,774 by 2026-09-09, and it is being ported out of bash into
.claude/rediacc_hooks/tests/ -- so the citation is dated on purpose and the
large-file control below is what keeps the measurement reproducible after the
file it names is gone.

WHY A LOCALLY-DEFINED FUNCTION IS THE TEST, and not "any pipe into grep -q".
There are 115 `| grep -q` sites under pipefail in this repo. What makes the shape
MOST dangerous is a producer whose output SCALES WITH ITS INPUT -- a function that
reads a file, filters a corpus, enumerates a tree. Judging "is the producer a
function this file defines" is a property this gate owns, independent of what the
code claims, which is the trap gates.md warns about: an assertion that re-asks a
question the code already answered cannot fire.

THE EXEMPTION BELOW USED TO BE STATED AS SAFETY, AND THAT WAS WRONG. This block
previously read "almost all are harmless: `printf '%s' "$x" | grep -q` has a
bounded producer that finishes before anything can race". Falsified on 2026-08-31
by CI run 33432878128, job 99628247967:

    .ci/scripts/test/gates/test-run-sh.sh:67
    if printf '%s' "$QA" | grep -q 'return 1'; then

`$QA` is 1129 bytes, far inside the 64 KB pipe buffer, and the match sits on line
23 of ~30. It still raced: the log carries `printf: write error: Broken pipe` and
the branch took the else, reporting "quality_all has no failure path" against code
whose `return 1` grep had just FOUND. EPIPE does not depend on the buffer filling.
It depends on whether `grep -q` has already exited and CLOSED the read end when
the write syscall lands, and that is pure scheduling. A bounded producer is less
likely to lose the race, never immune to it.

So the narrow scope here is a matter of BLAST RADIUS, not of safety: the scaling
producers are converted and gated at zero, and the bounded ones remain a known,
measured flake source rather than a proven-safe pattern. Do not read this gate's
green as a claim that a bounded `printf | grep -q` is correct. It is not; it is
untriaged.

THE FIX IS ALWAYS THE SAME and is a drop-in: command substitution reads the
producer to completion, so there is no signal to race.

    [ -n "$(producer | grep -E '<pattern>')" ]

NO BASELINE, deliberately. The class was 13 sites and every one was converted, so
this gate stands at zero with an anti-vacuity floor. A baseline here would have
recorded ten provably-safe sites as debt and left three real risks sitting in a
list that says "known, fine" -- and a stale baseline entry is a slot where the
next regression hides.

THE MECHANISM CONTROL ASKS THE OPERATING SYSTEM, not this gate's regex.
Everything else here is pattern matching, and pattern matching cannot tell you
the mechanism is real on the machine the gate runs on. If SIGPIPE-under-pipefail
ever stops flipping the verdict, this gate is guarding a myth and should say so
rather than keep passing. THE PRODUCER MUST BE ONE THAT DIES ON SIGPIPE, and not
every command does. Measured on this host (uutils coreutils 0.8.0, ugrep 7.8.4):
`grep -v`, `sed` and `awk` all exhibit the race; `cat` does NOT -- uutils cat
reports success on a 300 KB producer that was killed mid-write. The first draft
of this control used `cat` and therefore could not reproduce the very mechanism
the gate exists for; the control refused to pass, which is what caught it.
`grep -v` is used because that is literally what the defect's producer was:
`advice_only()` in check-ci-watch-recipe.sh is a `grep -vE`.

THE FIXTURE IS ASSEMBLED AT RUNTIME so this file's own TEXT never carries the
racing shape contiguously. Written out literally, the gate flagged its own control
fixture -- correctly, by its rule, since the fixture IS the bad shape on purpose.
Self-exemption was the wrong answer: a gate that skips its own file stops policing
the one script most likely to grow this bug next. The same runtime-concatenation
convention test-hooks.sh uses for banned tokens.

COMMENTS AND STRING LITERALS ARE BOTH STRIPPED FIRST, and the second one was
learned the hard way: this gate flagged ITSELF the moment it became a tracked
file, because its own message text says "no racing <function> | grep -q ..." and
`pass` is a function it defines. Four findings, every one of them prose describing
the very bug the gate exists for. That is the mention-as-execution class, this
time inside the gate written to catch a different class -- and its own fixture
heredoc (`if producer "$2" | grep -q ...`) is real code that must stay quoted-out
too, since it is a CONTROL, not a defect. `sed` blanks quoted spans rather than
deleting the line, so line numbers stay honest in the report.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE CORPUS IS `git ls-files`, INVOKED, NOT REIMPLEMENTED. The twin's pathspecs
(`.ci/scripts/**/*.sh`, `scripts/**/*.sh`, `.claude/hooks/**/*.sh`) are matched by
git's wildmatch, which by default lets `*` cross a `/`. A `pathlib.rglob`
rewrite would be a SECOND definition of the corpus and would drift from the
twin's the first time a directory moved -- and a corpus that quietly narrows is
precisely the vacuity this gate's own floor exists to catch. It is a subprocess.

THE COLOUR CONDITION IS THE TWIN'S BUG, CARRIED. `[ -t 1 ]` tests STDOUT and
`fail()` writes its coloured line to STDERR, which is the 11-file variant
`rediacc_ci.log` was written to replace. `rediacc_ci.log` is deliberately NOT used
here: it would decide colour from stderr and disable it under CI, so the two
implementations would emit different bytes in exactly the environment CI runs in.
Reported as a twin finding instead of repaired.

THE MECHANISM CONTROL IS RUN FOR REAL, in a bash child, with a 300 KB producer.
It is the one control that would be worthless as a pure-Python assertion: the
whole claim is about what the OPERATING SYSTEM does to a writer whose reader has
gone, and Python cannot answer that on bash's behalf. Both implementations
therefore spawn the same fixture, and if the host ever stops reproducing the race
BOTH go red together, which is the correct joint behaviour.

THE SED IS THREE SUBSTITUTIONS IN ORDER, per line: strip from the first `#` to
end of line, then blank single-quoted spans, then blank double-quoted spans.
Order matters -- a `#` inside a string is removed before the string is blanked,
which is the twin's behaviour and not obviously right, but changing it would
change which lines are findings.

`\\b` AND `[[:space:]]` are written out rather than abbreviated. `\\b` means the
same thing in both engines for ASCII identifiers; `[[:space:]]` does not equal
Python's `\\s`, which additionally matches U+00A0 and U+2028, so the class is
spelled literally.

SORT ORDER IS BYTEWISE IN BOTH. The twin pipes function names through `sort -u`
with no locale pinned, and the differential harness exports LC_ALL=C; Python's
`sorted()` on ASCII identifiers is the same order. Named because a locale-aware
sort would reorder findings, and while the comparator treats findings as an
unordered multiset, a human diffing the two streams would see churn.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The corpus, as git pathspecs. Handed to `git ls-files` verbatim; see the port
# notes for why this is not rewritten as a glob walk.
# `:(glob)` IS LOAD-BEARING: without it git reads `**` as demanding a slash, so
# these matched nothing at depth 1 and the corpus silently skipped six tracked
# shell files. Measured 2026-09-08: 471 before, 477 after. Kept BYTE-EQUAL to the
# twin's spelling at `check-pipefail-grep-q.sh`, since the shadow ledger compares
# the two verdicts and a corpus difference would read as a behavioural divergence.
PATHSPECS = (
    ":(glob).ci/scripts/**/*.sh",
    ":(glob)scripts/**/*.sh",
    ":(glob).claude/hooks/**/*.sh",
)

# `grep -qE 'set -[a-z]*o pipefail|set -o pipefail'`. Only a script that actually
# sets pipefail can have the bug; without it the pipeline reports grep's status
# and the match stands.
PIPEFAIL_RE = re.compile(r"set -[a-z]*o pipefail|set -o pipefail")

# `grep -oE '^[A-Za-z_][A-Za-z0-9_]*\(\)'` -- a function DEFINITION at column one,
# with no space before the parentheses.
FUNCDEF_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)")

# The three sed expressions, in the twin's order. See the port notes.
_STRIP_COMMENT = (re.compile(r"#.*$"), "")
_BLANK_SQUOTE = (re.compile(r"'[^']*'"), "''")
_BLANK_DQUOTE = (re.compile(r'"[^"]*"'), '""')

# POSIX [[:space:]], written out.
_SPACE = r"[ \t\n\v\f\r]"

# The 200-byte pad and 1500 lines of the mechanism fixture: ~300 KB, well past the
# 64 KB pipe buffer, so the producer BLOCKS and grep -q's early exit kills it.
# Under the buffer nothing races and the control would silently prove nothing --
# which is exactly how the first attempt at a large-file control in
# check-ci-watch-recipe.sh came out vacuous.
MECH_PAD_WIDTH = 200
MECH_LINES = 1500

# ASSEMBLED AT RUNTIME so this file's own text never carries the racing shape
# contiguously. See the twin's note, carried in the module docstring.
_GQ = "grep -q"


def strip_code(line: str) -> str:
    """The twin's `sed -e 's/#.*$//' -e "s/'[^']*'/''/g" -e 's/"[^"]*"/""/g'`.

    Blanks rather than deletes, so line numbers in the report stay honest.
    Exported so `--selftest` can drive the mention-as-execution direction without
    writing a file.
    """
    for pattern, replacement in (_STRIP_COMMENT, _BLANK_SQUOTE, _BLANK_DQUOTE):
        line = pattern.sub(replacement, line)
    return line


def local_functions(text: str) -> list[str]:
    """`grep -oE '^[A-Za-z_][A-Za-z0-9_]*\\(\\)' | tr -d '()' | sort -u`."""
    names = {match.group(1) for line in text.split("\n") if (match := FUNCDEF_RE.match(line))}
    return sorted(names)


def offenders_in(text: str) -> list[str]:
    """`offenders <file>` -- one `<line>:<text>` per racing pipeline. Empty is clean.

    The order is the twin's: function names in sorted order, and within each name
    the file's own line order, because the twin runs one `grep -n` per name. A
    line naming two different local functions is therefore reported TWICE, which
    is real and is preserved.
    """
    if not PIPEFAIL_RE.search(text):
        return []
    names = local_functions(text)
    if not names:
        return []
    lines = text.split("\n")
    stripped = [strip_code(line) for line in lines]
    hits: list[str] = []
    for name in names:
        # `grep -nE "\b${fn}\b[^|]*\|[[:space:]]*grep -q"` -- a CALL to that
        # function, then a pipe, then grep -q, in CODE.
        pattern = re.compile(r"\b%s\b[^|]*\|%s*%s" % (re.escape(name), _SPACE, re.escape(_GQ)))
        for number, line in enumerate(stripped, start=1):
            if pattern.search(line):
                hits.append("%d:%s" % (number, line))
    return hits


def offenders(path: pathlib.Path) -> list[str]:
    """`offenders` over a file on disk. An unreadable file is silent, as `2>/dev/null` is."""
    try:
        return offenders_in(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []


def scan_files(root: pathlib.Path) -> list[str]:
    """`git -C "$ROOT" ls-files <pathspecs> 2>/dev/null`, as repo-relative strings."""
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", *PATHSPECS],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
        check=False,
    )
    return (completed.stdout or "").split("\n")


def mechanism_output(tmp: pathlib.Path) -> str:
    """Run the SIGPIPE fixture in a real bash child. "MISSED" means the race is live.

    THE ONE CONTROL THAT ASKS THE OPERATING SYSTEM. See the module docstring: a
    pure-Python assertion here would prove something about Python, and the claim
    is about what bash and the kernel do to a writer whose reader has exited.
    """
    mech = tmp / "mech.sh"
    mech.write_text(
        "set -uo pipefail\n"
        'producer() { grep -v ZZZ_NEVER_MATCHES "$1"; }\n'
        "if producer \"$2\" | %s 'NEEDLE'; then echo MATCHED; else echo MISSED; fi\n" % _GQ,
        encoding="utf-8",
    )
    big = tmp / "big.txt"
    pad = "x" * MECH_PAD_WIDTH
    with big.open("w", encoding="utf-8") as handle:
        handle.write("NEEDLE\n")
        for _ in range(MECH_LINES):
            handle.write(pad + "\n")
    completed = subprocess.run(
        ["bash", str(mech), "x", str(big)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
        check=False,
    )
    # `mech_out="$(...)"` strips trailing newlines, and the comparison is `=`.
    return (completed.stdout or "").rstrip("\n")


class _Report:
    """The twin's `fail` / `pass` pair, colours and streams included.

    THE COLOUR CONDITION IS THE TWIN'S: `[ -t 1 ]` tests STDOUT while `fail`
    writes to STDERR. `rediacc_ci.log` is deliberately not used; see the port
    notes.
    """

    def __init__(self, *, colour: bool | None = None) -> None:
        if colour is None:
            colour = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.red = "\033[0;31m" if colour else ""
        self.green = "\033[0;32m" if colour else ""
        self.nc = "\033[0m" if colour else ""
        self.fails = 0

    def fail(self, message: str) -> None:
        print("%s✗%s %s" % (self.red, self.nc, message), file=sys.stderr)
        self.fails += 1

    def ok(self, message: str) -> None:
        print("%sok%s   %s" % (self.green, self.nc, message))


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean, 1 on any failed control or any racing pipeline.

    `--selftest` is intercepted BEFORE any real scan, which is the addition the
    twin does not have. The twin takes no arguments, so no caller passes it.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    report = _Report()

    with tempfile.TemporaryDirectory() as tmpname:
        tmp = pathlib.Path(tmpname)

        mech_out = mechanism_output(tmp)
        if mech_out == "MISSED":
            report.ok(
                "control: SIGPIPE under pipefail really does flip a matching pipeline to false"
            )
        else:
            report.fail(
                "CONTROL DID NOT FIRE: a matching `producer | grep -q` reported '%s' on a 300 KB "
                "producer. The mechanism this gate exists for did not reproduce, so its green "
                "means nothing here." % mech_out
            )

        bad = 'set -o pipefail\nbody() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % _GQ
        if offenders_in(bad):
            report.ok("control: a local function piped into grep -q is detected")
        else:
            report.fail("CONTROL DID NOT FIRE: the racing shape went undetected")

        fixed = (
            'set -o pipefail\nbody() { cat "$1"; }\nif [ -n "$(body "$1" | grep x)" ]; then :; fi\n'
        )
        if not offenders_in(fixed):
            report.ok("control: the command-substitution form is NOT flagged")
        else:
            report.fail("GATE IS OVER-BROAD: the sanctioned fix was flagged")

        bounded = 'set -o pipefail\nif printf "%%s" "$x" | %s y; then :; fi\n' % _GQ
        if not offenders_in(bounded):
            report.ok("control: a bounded producer (printf, not a local function) is not flagged")
        else:
            report.fail("GATE IS OVER-BROAD: a bounded builtin producer was flagged")

        nopipefail = 'body() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % _GQ
        if not offenders_in(nopipefail):
            report.ok("control: without pipefail the same shape is harmless and not flagged")
        else:
            report.fail("GATE IS OVER-BROAD: flagged a file that never sets pipefail")

        comment = 'set -o pipefail\nbody() { cat "$1"; }\n# never write: body "$1" | %s x\n' % _GQ
        if not offenders_in(comment):
            report.ok("control: prose describing the shape is not committing it")
        else:
            report.fail(
                "GATE IS OVER-BROAD: a COMMENT naming the shape was read as code -- the "
                "mention-as-execution class"
            )

        # ---- the real tree ----------------------------------------------------
        scanned = 0
        found: list[str] = []
        for rel in scan_files(root):
            if not rel:
                continue
            target = root / rel
            if not target.is_file():
                continue
            scanned += 1
            found.extend("%s:%s" % (rel, hit) for hit in offenders(target))

        # ANTI-VACUITY: scanning nothing must FAIL, never pass quietly.
        if scanned == 0:
            report.fail(
                "scanned ZERO files -- the pathspec matched nothing, so a green here would "
                "mean nothing"
            )
        elif not found:
            report.ok(
                "no racing `function | grep -q` under pipefail in %d scanned file(s)" % scanned
            )
        else:
            report.fail(
                "%d racing pipeline(s): a local function piped into grep -q under pipefail"
                % len(found)
            )
            # `printf '    %s\n' "${found[@]}"` -- an ARRAY, so the format is
            # reused per element and every line carries the four-space indent.
            for hit in found:
                print("    %s" % hit, file=sys.stderr)
            print(file=sys.stderr)
            print(
                "  grep -q exits at its first match and SIGPIPEs the producer; pipefail then",
                file=sys.stderr,
            )
            print(
                "  makes that 141 the pipeline's status, so a pipeline that MATCHED reports",
                file=sys.stderr,
            )
            print(
                "  false. It only bites once the producer outruns the 64 KB pipe buffer, so",
                file=sys.stderr,
            )
            print("  it passes on small inputs and flips under load.", file=sys.stderr)
            print(file=sys.stderr)
            print(
                """  Fix, a drop-in:  [ -n "$(producer | grep -E '<pattern>')" ]""", file=sys.stderr
            )

        print()
        if report.fails == 0:
            print("%s✓%s pipefail/grep -q: %d file(s) clean." % (report.green, report.nc, scanned))
            print("  Blind spot, stated so the green is not read as more than it is: this sees")
            print("  only LOCALLY-DEFINED producers. A racing pipeline whose producer is an")
            print("  external command with unbounded output is real and invisible here.")
            return 0
        print("%s✗%s pipefail/grep -q: %d failure(s)." % (report.red, report.nc, report.fails))
        return 1


def selftest() -> int:
    """Plant each violation, prove it fires; remove it, prove it does not.

    BOTH DIRECTIONS FOR EVERY CONTROL. The twin's own five fixture controls are
    re-asserted here against `offenders_in` directly, plus the shapes the twin
    does not cover: two functions on one line, a line number that survives
    quoting, and the empty corpus.
    """
    ctl = Controls("pipefail-grep-q", floor=18, verbose=True)

    bad = 'set -o pipefail\nbody() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % _GQ
    ctl.check("CONTROL: the racing shape is detected", len(offenders_in(bad)), 1)
    ctl.check("...and it is reported at the RIGHT line", offenders_in(bad)[0].split(":")[0], "3")

    ctl.check(
        "MIRROR: the command-substitution fix is not flagged",
        offenders_in(
            'set -o pipefail\nbody() { cat "$1"; }\nif [ -n "$(body "$1" | grep x)" ]; then :; fi\n'
        ),
        [],
    )
    ctl.check(
        "MIRROR: a bounded builtin producer is not flagged",
        offenders_in('set -o pipefail\nif printf "%%s" "$x" | %s y; then :; fi\n' % _GQ),
        [],
    )
    ctl.check(
        "MIRROR: without pipefail the same shape is harmless",
        offenders_in('body() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % _GQ),
        [],
    )
    ctl.check(
        "MIRROR: a COMMENT naming the shape is not committing it",
        offenders_in(
            'set -o pipefail\nbody() { cat "$1"; }\n# never write: body "$1" | %s x\n' % _GQ
        ),
        [],
    )
    # THE ONE THAT COST THIS GATE ITS FIRST GREEN: its own message text names a
    # function it defines, inside a string literal.
    ctl.check(
        "MIRROR: the shape inside a STRING LITERAL is prose, not code",
        offenders_in(
            'set -o pipefail\npass() { echo "$*"; }\necho "no racing pass | %s here"\n' % _GQ
        ),
        [],
    )

    ctl.check(
        "VACUITY: a file defining no function cannot offend",
        offenders_in("set -o pipefail\nif x | %s y; then :; fi\n" % _GQ),
        [],
    )
    ctl.check("VACUITY: an empty file is clean", offenders_in(""), [])

    # `pipefail` spellings the twin's alternation accepts.
    for spelling in ("set -o pipefail", "set -euo pipefail", "set -uo pipefail"):
        ctl.check(
            "CONTROL: `%s` counts as setting pipefail" % spelling,
            len(
                offenders_in(
                    '%s\nbody() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % (spelling, _GQ)
                )
            ),
            1,
        )

    # The stripper, in both directions.
    ctl.check("strip: a comment is removed", strip_code("code # body | %s x" % _GQ), "code ")
    ctl.check("strip: a single-quoted span is blanked", strip_code("a 'b c' d"), "a '' d")
    ctl.check("strip: a double-quoted span is blanked", strip_code('a "b c" d'), 'a "" d')
    ctl.check(
        "strip: unquoted code survives untouched", strip_code("body | grep x"), "body | grep x"
    )

    # Function-name extraction, both directions.
    ctl.check("funcs: a definition at column one is found", local_functions("body() {\n"), ["body"])
    ctl.check("funcs: an INDENTED definition is not", local_functions("  body() {\n"), [])
    ctl.check(
        "funcs: a space before the parens is not the shape", local_functions("body () {\n"), []
    )
    ctl.check(
        "funcs: names come back sorted and unique",
        local_functions("zed() {\nabe() {\nzed() {\n"),
        ["abe", "zed"],
    )

    # A line naming two local functions is reported twice, once per name. Pinned
    # because it looks like a duplicate-suppression bug and is the twin's shape.
    two = "set -o pipefail\nabe() { :; }\nzed() { :; }\nif abe zed | %s x; then :; fi\n" % _GQ
    ctl.check("a line naming TWO local functions is reported twice", len(offenders_in(two)), 2)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
