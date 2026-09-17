r"""Control-first gates must prove their plant actually landed.

Ported from `.ci/scripts/quality/check-control-vacuity.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHAT THE TWIN ENFORCES, carried over from its own header verbatim because the argument IS the gate:

    Gate: a control-first gate that PLANTS its defect by pattern substitution must
    prove the plant landed before trusting the control.

    Why. A control-first gate earns its green by re-running its assertions against
    a copy of the source mutated to carry the original defect: if the mutant passes,
    the gate cannot detect what it exists for and fails itself. That argument has a
    hole when the mutation is a PATTERN substitution -- `${SRC//needle/replacement}`
    or `sed 's/needle/replacement/'`. Reword the line the needle matches and the
    substitution silently produces an identical copy. The control then "passes"
    against unmutated source and the gate reports a green that proves nothing.

    This is not hypothetical: on 2026-08-24 check-devcontainer-scripts.sh had exactly
    this happen when the line its A-control targeted was rewritten, and the gate
    announced CONTROL IS VACUOUS rather than going green -- because it had the guard
    this check now requires of every sibling.

    A control built by CONSTRUCTION rather than substitution (concatenating a known
    bad entry, injecting a key with python) cannot fail to apply, so it is exempt.
    The rule keys on how the mutant is BUILT, not on whether a control exists.

    Control-first itself: the control below strips a real gate's guard and requires
    this check to catch it.

THE THREE EXCLUSIONS INSIDE `builds_by_substitution`, all carried, because each one was paid for by a false positive:

  * A PREFIX substitution CANNOT go vacuous. `s/^/.../` has an EMPTY needle
    anchored at line start: it always matches, so it can never silently produce
    an identical copy. Two shapes in real use here, `sed 's/^/         /'`
    indenting a message and `seq 1 N | sed 's/^/echo /'` GENERATING a fixture
    from nothing. "Flagging them (measured 2026-08-26 on check-devbox-exec.sh
    and check-shell-size.sh) demanded a proof-of-plant for a plant that does not
    exist."
  * COMMENTS ARE STRIPPED FIRST, the same rule check-toolchain-pins.sh's A6
    already applies: judge the code, not the words describing it. "Measured
    2026-08-26 -- this gate flagged check-shell-size.sh for a `${n//...}` that
    existed ONLY inside a comment explaining why that construct was avoided
    here. A gate that reads its own documentation as the thing it forbids cannot
    be satisfied except by deleting the explanation."
  * `sed -i "$expr"` where the expression is held in a variable, so no literal
    `s///` appears on the line. "Missing the third mis-exempted the two gates
    that motivated this check."

THE SCOPE IS STATED, NOT LEFT TO THE GLOB, and the twin's reason is carried with it: "This check parses BASH, so its enumeration is `check-*.sh` and every `check_*.py` gate is outside it. That is a real limit, and on 2026-08-28 it was invisible: a reader saw a green with no hint that 21 sibling gates had not been looked at. Measured the same day, which is why this is a printed
COUNT and not new parsing: of the 21 Python gates, ZERO build a control mutant by substitution." So the number of unscanned gates is part of the green line.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`[[:punct:]]` IS NOT THE SAME SET IN EVERY grep, MEASURED 2026-09-06 ON THIS HOST. `grep` here is ugrep 7.8.4, whose `[[:punct:]]` is the Unicode PUNCTUATION
categories and therefore EXCLUDES the nine ASCII symbols `$ + < = > ^ ` | ~`,
which GNU grep and POSIX both include. Verified by running `grep -oE '[[:punct:]]'` over the printable ASCII range: ugrep returned
`!"#%&'()*,-./:;?@[\]_{}` and nothing else.

The port uses the WIDER, POSIX set. The difference is unobservable on every shape actually in use, because the character the pattern requires immediately before the `s` is the quote opening a sed expression (`sed 's/`, `sed "s/`), and a quote is punctuation under both readings. A file containing `sed $s/` would be flagged by the port and not by ugrep; no such file exists, and
`tests/test_quality_control_vacuity.py` compares the port against the LIVE grep pipeline file by file across the whole gate directory so a future one would show up as a failing test rather than as a silent divergence.

COLOUR IS DECIDED ON A DIFFERENT STREAM. The twin sets RED/GREEN on `[ -t 1 ]` -- stdout -- and then writes its coloured `✗` lines to STDERR. That is the 11-file variant `rediacc_ci.log`'s docstring documents as a bug: redirect one stream and not the other and the colour lands in the wrong place. `log.error` tests the stream it writes to. Under the differential neither stream is a
terminal, so both produce the same bytes; on a developer's terminal with stdout redirected the twin emits escapes into a pipe and the port does not. Reported as a twin defect, not repaired in the twin.

THE BANNER AND THE GREEN LINE ARE STDOUT, the findings are stderr, and the split is the twin's. `echo` for the two summary lines, `>&2` for every `fail`. Carried exactly, because `scripts/lib/shadow-gate.ts` reads both streams and a moved line changes the chatter/finding split.

`sed '/.../,+2d'` IS A RANGE, NOT A PER-LINE DELETE. It removes the matching line and the two after it, then RESUMES looking for a new start. A port that deleted only matching lines would leave the two lines after the guard behind and the control's stripped copy would still carry them; a port that stopped after the first range would miss a second guard. Both are wrong in the same
direction: they make the control easier to pass.
"""

import glob
import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls


def _joined(*rows: str) -> str:
    """`"\n".join(rows)` behind a call. The rows stay one per line.

    A helper rather than a literal join because ruff's FLY002 rewrites a join over a LITERAL list into an f-string, and a ten-line shell fixture written as one f-string is unreadable. Passing the rows as arguments keeps the fixture legible and gives the linter nothing static to fold.
    """
    return "\n".join(rows)


# POSIX [[:space:]] and [[:punct:]], written out. `\s` and `\w` are wider in Python than in a POSIX bracket expression, and the difference is exactly the kind that makes a port quietly see more or less than its twin.
SPACE = r"[ \t\n\v\f\r]"
PUNCT = r"[!-/:-@\[-`{-~]"

# Does this file run a control at all? Five spellings, measured across the gate directory by the twin and carried unchanged.
HAS_CONTROL = re.compile(
    r"CONTROL DID NOT FIRE|control could not plant|CONTROL IS VACUOUS|"
    r"control_must_fail|^control\(\)",
)

# Stage 1 of `builds_by_substitution`: drop comment lines. `grep -vE`.
COMMENT_LINE = re.compile(r"^%s*#" % SPACE)

# Stage 2: drop PREFIX substitutions, which cannot go vacuous. `grep -vE`.
PREFIX_SED = re.compile(r"sed [^&]*%ss[/@|#]\^[/@|#]" % PUNCT)

# Stage 3: does what remains build a mutant by pattern substitution? `grep -qE`.
SUBSTITUTION = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*//|sed [^&]*%ss[/@|#]|sed -i" % PUNCT)

# Either shape counts as proof the plant landed:
#   [[ "$MUTANT" == "$SRC" ]]   -- substitution produced an identical copy
# grep -q '<marker>' <mutant> -- the planted marker is present
PROVES_IDENTICAL = re.compile(r'\[\[ "\$[A-Za-z_][A-Za-z0-9_]*" == "\$[A-Za-z_][A-Za-z0-9_]*" \]\]')
PROVES_MARKER = re.compile(r"grep -[a-z]*q[a-z]* .+(\$TMP|\$MUTANT|mutant|broken)")

# The gate the CONTROL mutilates, and the guard line it removes. Named as constants so the failure message and the strip cannot drift apart.
CONTROL_GATE = "check-review-turn-capacity.sh"
CONTROL_GUARD = re.compile(r'\[\[ "\$MUTANT" == "\$FN" \]\]')

# The substitution the stripped copy must still carry. Without this the control would "fire" against a copy that had lost the thing being tested.
CONTROL_STILL_SUBSTITUTES = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*//")

# This file is not its own subject.
SELF = "check-control-vacuity.sh"

BANNER = "check-control-vacuity: every pattern-substitution control proves its plant landed"


def read_lines(path) -> list[str]:
    """A file's lines as grep would see them: no terminator, no trimming.

    `errors="replace"` rather than `surrogateescape`, because nothing here is
    written back out: every finding names a BASENAME, never file content.
    """
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8", "replace")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def has_control(lines: list[str]) -> bool:
    """Does this file run a control at all? `grep -qE` over five spellings."""
    return any(HAS_CONTROL.search(line) for line in lines)


def builds_by_substitution(lines: list[str]) -> bool:
    """Does it build its control input by PATTERN SUBSTITUTION, the fragile kind?

    THREE STAGES, IN ORDER, because each one is a `grep` in a pipeline and the order decides the answer. Stripping comments AFTER testing for a substitution would flag a file for a construct that exists only in the prose explaining why it is avoided, which is the 2026-08-26 false positive on check-shell-size.sh.
    """
    kept = [line for line in lines if not COMMENT_LINE.search(line)]
    kept = [line for line in kept if not PREFIX_SED.search(line)]
    return any(SUBSTITUTION.search(line) for line in kept)


def proves_plant_landed(lines: list[str]) -> bool:
    """Does it prove the plant landed? Either shape counts."""
    if any(PROVES_IDENTICAL.search(line) for line in lines):
        return True
    return any(PROVES_MARKER.search(line) for line in lines)


def strip_guard(lines: list[str]) -> list[str]:
    """`sed '/<guard>/,+2d'`: delete the guard line and the two after it.

    A RANGE, and it can start again. See the port notes for why the two obvious simplifications both make the control easier to pass.
    """
    out: list[str] = []
    remaining = 0
    for line in lines:
        if remaining > 0:
            remaining -= 1
            continue
        if CONTROL_GUARD.search(line):
            remaining = 2
            continue
        out.append(line)
    return out


class Failures:
    """The `fails` counter and the `fail()` that increments it.

    An object rather than a module global so `selftest` can drive several scans in one process without a previous case's count leaking into the next.
    """

    def __init__(self) -> None:
        self.count = 0

    def fail(self, message: str) -> None:
        log.error(message)
        self.count += 1


def self_prose_control() -> str | None:
    """Prove the detector reads CODE and not its own documentation. None is OK.

    Both directions, exactly as the twin runs them: a comment ABOUT a substitution must not register, and a real substitution in code must.
    """
    with tempfile.TemporaryDirectory() as tmp:
        probe = pathlib.Path(tmp) / "probe.sh"
        probe.write_text(
            "#!/usr/bin/env bash\n"
            "# we deliberately avoid ${SRC//needle/repl} in this file\n"
            "echo hi\n",
            encoding="utf-8",
        )
        if builds_by_substitution(read_lines(probe)):
            return "SELF-PROSE CONTROL FAILED: a comment about a substitution read as one"
        probe.write_text('#!/usr/bin/env bash\nMUTANT="${SRC//needle/repl}"\n', encoding="utf-8")
        if not builds_by_substitution(read_lines(probe)):
            return "SELF-PROSE CONTROL FAILED: a REAL substitution in code went undetected"
    return None


def audit(gate_dir: pathlib.Path, failures: Failures) -> tuple[int, int]:
    """Walk `check-*.sh` and rule on each. Returns (checked, exempt).

    SORTED, matching bash's glob expansion under LC_ALL=C. The order is not the
    verdict, but it is the output, and a reader diffing the two implementations' stderr side by side is the cheapest review this port will ever get.
    """
    checked = 0
    exempt = 0
    for path in sorted(glob.glob(str(gate_dir / "check-*.sh"))):
        candidate = pathlib.Path(path)
        if not candidate.is_file():
            continue
        base = candidate.name
        if base == SELF:
            continue
        lines = read_lines(candidate)
        if not has_control(lines):
            continue

        if not builds_by_substitution(lines):
            exempt += 1
            continue

        checked += 1
        if not proves_plant_landed(lines):
            failures.fail(
                "%s builds its control by pattern substitution but never proves "
                "the plant landed." % base
            )
            # STDERR, indented, so `scripts/lib/shadow-gate.ts` attaches these four lines to the finding above them. The twin prints them with bare `echo ... >&2`; the indent is the contract.
            print(
                "      Reword the targeted line and its control passes against UNMUTATED source,",
                file=sys.stderr,
            )
            print("      reporting a green that proves nothing. Add one of:", file=sys.stderr)
            print(
                '        [[ "$MUTANT" == "$SRC" ]] && fail \'...could not plant its defect...\'',
                file=sys.stderr,
            )
            print(
                "        grep -q '<planted marker>' \"$TMP/broken.sh\" || fail '...'",
                file=sys.stderr,
            )
    return checked, exempt


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 on any failure.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments and ignores any it is given, so no caller can be passing it.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    gate_dir = root / ".ci" / "scripts" / "quality"

    problem = self_prose_control()
    if problem is not None:
        # STDERR, unmarked, exactly as the twin prints it. Not a log.error: the twin uses a bare `echo ... >&2` here and the missing glyph is what makes this line chatter rather than a finding on both sides.
        print(problem, file=sys.stderr)
        return 1

    print(BANNER)

    failures = Failures()
    checked, exempt = audit(gate_dir, failures)

    # ANTI-VACUITY, per .claude/skills/testing/gates.md: discovering zero inputs must FAIL. A corpus that silently collapses to nothing is exactly how this check would stop protecting anything while still printing a tick.
    if checked == 0:
        failures.fail(
            "no pattern-substitution controls found at all \u2014 the corpus collapsed to zero."
        )
        print(
            "      Either the glob no longer matches the gate directory, or has_control/",
            file=sys.stderr,
        )
        print(
            "      builds_by_substitution stopped recognising the shapes in use.", file=sys.stderr
        )

    # ----------------------------------------------------------------------- CONTROL: strip a real gate's vacuity guard and require this check to catch it. Without this, a green above could mean "every gate complies" OR "the detector stopped recognising the guard shape", and those look identical. -----------------------------------------------------------------------
    control_src = gate_dir / CONTROL_GATE
    if control_src.is_file():
        stripped = strip_guard(read_lines(control_src))
        if not any(CONTROL_STILL_SUBSTITUTES.search(line) for line in stripped):
            failures.fail(
                "CONTROL IS VACUOUS: the stripped copy lost its substitution too, "
                "so it proves nothing."
            )
        elif proves_plant_landed(stripped):
            failures.fail(
                "CONTROL DID NOT FIRE: a gate with its vacuity guard removed was still "
                "judged compliant, so this check cannot detect the defect it exists for."
            )
    else:
        failures.fail(
            "CONTROL SOURCE MISSING: %s is gone; repoint the control at another "
            "substitution-based gate." % control_src
        )

    if failures.count != 0:
        print(file=sys.stderr)
        print(
            "%d gate(s) have a control that can go vacuous undetected." % failures.count,
            file=sys.stderr,
        )
        return 1

    # STATE THE SCOPE, do not leave it to the glob. A future `.py` gate that mutates its own source by substitution would escape this check with nothing said, so the number of unscanned gates is part of the green line.
    py_unscanned = sum(1 for p in glob.glob(str(gate_dir / "check_*.py")) if os.path.isfile(p))

    # STDOUT, NOT log.info. The twin's last line is
    # `echo "${GREEN}\u2713${NC} $checked ..."`, which lands on stdout, and
    # `rediacc_ci.log` writes every message to stderr by design. Both spellings are CHATTER to `scripts/lib/shadow-gate.ts`, so the differential would score the two as equivalent either way; that is exactly why it has to be got right by reading the twin rather than by watching the comparator.
    print(
        "\u2713 %d pattern-substitution control(s) prove their plant landed; %d built by "
        "construction (exempt); %d python gate(s) NOT scanned here -- check:ci-python-control-plants owns them"
        % (checked, exempt, py_unscanned)
    )
    return 0


# The four shapes the detector must rule on, as one-line fixtures. Named rather than inlined so a reader can see the whole decision table at once.
_SUBSTITUTES = 'MUTANT="${SRC//needle/repl}"'
_SUBSTITUTES_SED = 'sed \'s/needle/repl/\' "$SRC" >"$TMP/broken.sh"'
_SUBSTITUTES_SED_I = 'sed -i "$expr" "$TMP/broken.sh"'
_PREFIX_ONLY = "echo \"$hits\" | sed 's/^/         /'"
_CONSTRUCTED = 'printf "%s\\n" "$known_bad" >>"$TMP/broken.sh"'


def selftest() -> int:
    """Plant each shape, prove it is classified; plant its mirror, prove it is not.

    BOTH DIRECTIONS FOR EVERY RULE. This gate's whole value is a DISTINCTION (substitution versus construction, code versus comment, prefix versus needle), and a distinction has two sides. A suite with only positive plants would be satisfied by a detector that answered "yes" to everything, which is the same gate as one that answered "no".
    """
    ctl = Controls("control-vacuity", floor=24, verbose=True)

    ctl.check("CONTROL: the self-prose control passes", self_prose_control(), None)

    # -- has_control -------------------------------------------------------
    for spelling in (
        "CONTROL DID NOT FIRE",
        "control could not plant",
        "CONTROL IS VACUOUS",
        "control_must_fail",
    ):
        ctl.check(
            "HAS_CONTROL: %r registers" % spelling, has_control(["fail '%s'" % spelling]), True
        )
    ctl.check(
        "HAS_CONTROL: a bare control() definition registers", has_control(["control()"]), True
    )
    ctl.check(
        "MIRROR: control() must be at column 1, an indented one does not register",
        has_control(["    control()"]),
        False,
    )
    ctl.check("MIRROR: an unrelated gate does not register", has_control(["echo hi"]), False)

    # -- builds_by_substitution -------------------------------------------
    ctl.check(
        "SUBST: bash pattern substitution registers", builds_by_substitution([_SUBSTITUTES]), True
    )
    ctl.check(
        "SUBST: an inline sed s/// registers", builds_by_substitution([_SUBSTITUTES_SED]), True
    )
    ctl.check(
        "SUBST: sed -i with the expression in a variable registers",
        builds_by_substitution([_SUBSTITUTES_SED_I]),
        True,
    )
    ctl.check(
        "MIRROR: a PREFIX substitution cannot go vacuous and is not the fragile kind",
        builds_by_substitution([_PREFIX_ONLY]),
        False,
    )
    ctl.check(
        "MIRROR: a generated fixture via sed 's/^/echo /' is not the fragile kind",
        builds_by_substitution(["seq 1 5 | sed 's/^/echo /'"]),
        False,
    )
    ctl.check(
        "MIRROR: a substitution inside a COMMENT is prose, not code",
        builds_by_substitution(["# we avoid ${SRC//needle/repl} here"]),
        False,
    )
    ctl.check(
        "MIRROR: an indented comment is still a comment",
        builds_by_substitution(["    # ${SRC//a/b}"]),
        False,
    )
    ctl.check(
        "MIRROR: building the mutant by CONSTRUCTION is exempt",
        builds_by_substitution([_CONSTRUCTED]),
        False,
    )

    # -- proves_plant_landed ----------------------------------------------
    ctl.check(
        "PROOF: the identical-copy guard registers",
        proves_plant_landed(['if [[ "$MUTANT" == "$SRC" ]]; then fail "..."; fi']),
        True,
    )
    ctl.check(
        "PROOF: a grep for the planted marker registers",
        proves_plant_landed(["grep -q 'PLANTED' \"$TMP/broken.sh\" || fail '...'"]),
        True,
    )
    ctl.check(
        "MIRROR: a gate with a substitution and no proof does not register",
        proves_plant_landed([_SUBSTITUTES, "echo done"]),
        False,
    )

    # -- strip_guard, the CONTROL's own mutation ---------------------------
    body = ["a", 'if [[ "$MUTANT" == "$FN" ]]; then', "  fail x", "fi", "b"]
    ctl.check(
        "STRIP: the guard line and the two after it are removed", strip_guard(body), ["a", "b"]
    )
    ctl.check(
        "STRIP: a second guard later in the file is also removed",
        strip_guard(body + list(body)),
        ["a", "b", "a", "b"],
    )
    ctl.check("MIRROR: a file with no guard is unchanged", strip_guard(["a", "b"]), ["a", "b"])

    # -- the whole gate, over a fixture gate directory ---------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        gate_dir = root / ".ci" / "scripts" / "quality"
        gate_dir.mkdir(parents=True)

        def write(name: str, body: str) -> None:
            (gate_dir / name).write_text(body, encoding="utf-8")

        def run() -> int:
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        # The control gate the CONTROL block strips. It must carry BOTH the substitution and the guard, or the control cannot fire.
        write(
            CONTROL_GATE,
            _joined(
                "#!/bin/bash",
                "# CONTROL DID NOT FIRE is mentioned here",
                'MUTANT="${FN//per_kloc=25/per_kloc=8}"',
                'if [[ "$MUTANT" == "$FN" ]]; then',
                '  fail "could not plant"',
                "fi",
                "",
            ),
        )
        write(
            "check-good.sh",
            _joined(
                "#!/bin/bash",
                "# CONTROL DID NOT FIRE",
                'MUTANT="${SRC//a/b}"',
                'if [[ "$MUTANT" == "$SRC" ]]; then fail "could not plant"; fi',
                "",
            ),
        )
        ctl.check("CONTROL: a compliant gate directory passes", run(), 0)

        write(
            "check-bad.sh",
            _joined(
                "#!/bin/bash",
                "# CONTROL DID NOT FIRE",
                'MUTANT="${SRC//a/b}"',
                "echo done",
                "",
            ),
        )
        ctl.check("PLANT: a substitution control with no proof reds", run(), 1)
        (gate_dir / "check-bad.sh").unlink()

        # THE VACUITY CASE. Remove every substituting gate and the corpus collapses; a gate that reported clean here would be reporting on nothing. The control gate stays so the CONTROL block still runs.
        (gate_dir / "check-good.sh").unlink()
        write(CONTROL_GATE, "#!/bin/bash\n# CONTROL DID NOT FIRE\necho hi\n")
        ctl.check("VACUITY: a corpus that collapsed to zero reds", run(), 1)

        # And the control source going missing is its own refusal.
        (gate_dir / CONTROL_GATE).unlink()
        write(
            "check-good.sh",
            _joined(
                "#!/bin/bash",
                "# CONTROL DID NOT FIRE",
                'MUTANT="${SRC//a/b}"',
                'if [[ "$MUTANT" == "$SRC" ]]; then fail "x"; fi',
                "",
            ),
        )
        ctl.check("REFUSAL: a missing control source reds", run(), 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
