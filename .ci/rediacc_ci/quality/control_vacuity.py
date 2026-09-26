r"""Control-first gates must prove their plant actually landed.

Ported from `.ci/scripts/quality/check-control-vacuity.sh`, which W7 P5 batch C2 retired once `.ci/shadow/w7p2-control-vacuity.observations.jsonl` asserted equivalence over five distinct trees.

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

    Control-first itself: the control below strips a real gate's proof and requires
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

THE SCOPE IS STATED, NOT LEFT TO THE GLOBS, and the twin's reason for stating it is why the scope eventually MOVED: "This check parses BASH, so its enumeration is `check-*.sh` and every `check_*.py` gate is outside it. That is a real limit, and on 2026-08-28 it was invisible: a reader saw a green with no hint that 21 sibling gates had not been looked at." The limit was
closed on 2026-09-21 rather than restated, when the last bash control in the tree was retired and the bash arm reached zero. The Python arm beside it is described where it is defined; the green line now counts both, so an arm that empties is visible instead of being a number nobody reads.

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

# The guard line the bash strip removes, kept because `strip_guard` is still the tested transliteration of `sed '/.../,+2d'`.
CONTROL_GUARD = re.compile(r'\[\[ "\$MUTANT" == "\$FN" \]\]')

# This file is not its own subject.
SELF = "check-control-vacuity.sh"

# --------------------------------------------------------------------------- THE PYTHON ARM, ADDED 2026-09-21 WITH THE RETIREMENT OF THE LAST BASH CONTROL.
#
# WHAT HAPPENED. `check-review-turn-capacity.sh` was the only file in the whole tracked tree carrying a bash control of any kind, let alone one built by pattern substitution: measured that day over `.ci/scripts/**`, `.claude/**`, `scripts/**` and `.github/**`, one hit. Retiring it leaves the bash arm below scanning a real directory and finding nothing, which is the state its own
# anti-vacuity refusal exists to announce. The subject did not disappear, it changed language, so the corpus follows it rather than the gate being re-floored to keep a green over nothing.
#
# WHAT THIS ARM ASKS, AND WHY IT IS NOT `check:ci-python-control-plants`. That gate asks whether the HARNESS was used, by AST, over control regions, and refuses a raw `X.replace(...)`. This one asks the question it has always asked, whether there is a PROOF the plant landed, and for Python the proof IS `rediacc_ci.controls.plant`, which raises `VacuousPlantError` on a needle
# that is absent or a mutant byte-identical to its fixture. So the finding here is a module that PLANTS while its `plant` does not resolve to that harness: no import of it, or a local `def plant` shadowing it. That is the false negative the sibling gate names in its own header ("a gate that merely counted `plant(` would read those call sites as compliant while they use no
# harness at all"), and it is the half an AST scan of control regions does not cover, because a shadowed `plant` is not a raw substitution.
#
# LINE SCANNING, WITH STRINGS AND DOCSTRINGS REMOVED FIRST, and the removal is not tidiness. This file's prose says plant(s) and plant(), `check_python_control_plants.py` embeds whole modules as triple-quoted fixtures including one that defines a local plant, and both read as code to a scanner that only drops comments. Measured across the corpus: with comments alone stripped,
# one false positive; with string literals and triple-quoted blocks stripped too, zero.
PY_SCOPE = (
    os.path.join(".ci", "rediacc_ci", "quality", "*.py"),
    os.path.join(".ci", "scripts", "quality", "check_*.py"),
)

# A triple-quote opener or closer, counted per line. An ODD count toggles the block; an even one is a single-line docstring and changes nothing.
PY_TRIPLE = re.compile(r'"""|\'\'\'')

# A single-line string literal, either quote, with escapes honoured.
PY_STRING = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

# A CALL to the plant harness, not an attribute access on something else.
PY_PLANT = re.compile(r"(?<![\w.])plant(?:_re)?\(")

# The import that makes `plant` the harness, and the local definition that stops it being the harness.
PY_HARNESS_IMPORT = re.compile(r"^%s*from rediacc_ci\.controls import [^#]*\bplant\b" % SPACE)
PY_LOCAL_PLANT = re.compile(r"^%s*def plant(?:_re)?%s*\(" % (SPACE, SPACE))

# The gate the CONTROL mutilates, relative to the repository root. The SUCCESSOR of the bash file this control used to name: `check-review-turn-capacity.sh` was retired in the same change, and its Python port carries the same seven plants through the harness.
CONTROL_GATE = os.path.join(".ci", "rediacc_ci", "quality", "review_turn_capacity.py")

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


def py_code_lines(lines: list[str]) -> list[str]:
    """`lines` with comments, docstrings and single-line string literals removed.

    THE THREE REMOVALS ARE ORDERED AND EACH ONE WAS PAID FOR. A triple-quoted block is dropped whole, because `check_python_control_plants.py` carries entire Python modules as fixtures and one of them defines a local plant that is a fixture, not a shadow. A comment line goes for the reason the bash arm gives. A string literal is blanked rather than dropped, so a call spanning
    the rest of the line still reads as code while the prose inside the quotes does not.
    """
    out: list[str] = []
    inside = False
    for line in lines:
        marks = len(PY_TRIPLE.findall(line))
        if inside:
            if marks % 2:
                inside = False
            continue
        if marks % 2:
            inside = True
            continue
        if COMMENT_LINE.search(line):
            continue
        out.append(PY_STRING.sub('""', line))
    return out


def py_plants(code: list[str]) -> bool:
    """Does this module build a mutant at all? A `plant()` or `plant_re()` call."""
    return any(PY_PLANT.search(line) for line in code)


def py_plant_is_proven(code: list[str]) -> bool:
    """Does the `plant` it calls RESOLVE to the harness that refuses a no-op?

    Two conditions, and the second is the one a token count cannot express: the harness must be imported, and no local definition may shadow it. A module that imports `plant` and then defines its own is calling the local one, and the import left behind reads as compliance.
    """
    if not any(PY_HARNESS_IMPORT.search(line) for line in code):
        return False
    return not any(PY_LOCAL_PLANT.search(line) for line in code)


def strip_harness_import(lines: list[str]) -> list[str]:
    """Drop the harness import. The Python analogue of the bash `sed '/guard/,+2d'`.

    ONE LINE, NOT A RANGE, because the proof here is the RESOLUTION of a name rather than an assertion occupying several lines. The stripped copy keeps every plant call, which is what makes it a mutant of the thing under test rather than a different file.
    """
    return [line for line in lines if not PY_HARNESS_IMPORT.search(line)]


class Failures:
    """The `fails` counter and the `fail()` that increments it.

    An object rather than a module global so `selftest` can drive several scans in one process without a previous case's count leaking into the next.
    """

    def __init__(self) -> None:
        self.count = 0

    def fail(self, message: str) -> None:
        log.error(message)
        self.count += 1


def audit_python(root: pathlib.Path, failures: Failures) -> tuple[int, int]:
    """Walk the Python gate corpus and rule on each. Returns (checked, exempt).

    SORTED WITHIN EACH GLOB, matching the bash arm and, more usefully, making the stderr of two runs comparable line by line.
    """
    checked = 0
    exempt = 0
    for pattern in PY_SCOPE:
        for path in sorted(glob.glob(str(root / pattern))):
            candidate = pathlib.Path(path)
            if not candidate.is_file():
                continue
            code = py_code_lines(read_lines(candidate))
            if not py_plants(code):
                exempt += 1
                continue
            checked += 1
            if py_plant_is_proven(code):
                continue
            failures.fail(
                "%s plants a control mutant whose `plant` does not resolve to "
                "rediacc_ci.controls, so nothing refuses a mutation that silently did "
                "nothing." % candidate.name
            )
            print(
                "      Import it (`from rediacc_ci.controls import plant`) and remove any local",
                file=sys.stderr,
            )
            print(
                "      definition of the same name. The harness raises VacuousPlantError on an",
                file=sys.stderr,
            )
            print(
                "      absent needle or an unchanged mutant; a local copy does not.",
                file=sys.stderr,
            )
    return checked, exempt


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
    sh_checked, sh_exempt = audit(gate_dir, failures)
    py_checked, py_exempt = audit_python(root, failures)
    checked = sh_checked + py_checked

    # ANTI-VACUITY, per .claude/skills/testing/gates.md: discovering zero inputs must FAIL. A corpus that silently collapses to nothing is exactly how this check would stop protecting anything while still printing a tick. THE SUM, NOT EITHER ARM: the bash half reached zero on 2026-09-21 by a deliberate retirement rather than by a broken glob, and refusing on that alone would
    # have turned a completed port into a red nobody could clear except by deleting the guard.
    if checked == 0:
        failures.fail(
            "no pattern-substitution controls found at all \u2014 the corpus collapsed to zero."
        )
        print(
            "      Either the globs no longer match the two gate directories, or has_control/",
            file=sys.stderr,
        )
        print(
            "      builds_by_substitution/py_plants stopped recognising the shapes in use.",
            file=sys.stderr,
        )

    # ----------------------------------------------------------------------- CONTROL: strip a real gate's proof and require this check to catch it. Without this, a green above could mean "every gate complies" OR "the detector stopped recognising the proof shape", and those look identical.
    #
    # THE CONTROL MOVED TO PYTHON WITH THE CORPUS. It used to strip the `[[ "$MUTANT" == "$FN" ]]` guard out of `check-review-turn-capacity.sh`; that file is retired and its port is the subject now. Removing the harness import leaves every `plant()` call standing while making none of them resolve to the thing that refuses a no-op, which is exactly the defect being detected.
    # -----------------------------------------------------------------------
    control_src = root / CONTROL_GATE
    if control_src.is_file():
        stripped = strip_harness_import(py_code_lines(read_lines(control_src)))
        if not py_plants(stripped):
            failures.fail(
                "CONTROL IS VACUOUS: the stripped copy lost its plants too, so it proves nothing."
            )
        elif py_plant_is_proven(stripped):
            failures.fail(
                "CONTROL DID NOT FIRE: a gate with its harness import removed was still "
                "judged compliant, so this check cannot detect the defect it exists for."
            )
    else:
        failures.fail(
            "CONTROL SOURCE MISSING: %s is gone; repoint the control at another "
            "gate that plants through the harness." % control_src
        )

    if failures.count != 0:
        print(file=sys.stderr)
        print(
            "%d gate(s) have a control that can go vacuous undetected." % failures.count,
            file=sys.stderr,
        )
        return 1

    # STATE THE SCOPE, do not leave it to the globs. Both arms are counted separately, because they answer the same question about two populations and a reader has to be able to see one of them reach zero.
    # STDOUT, NOT log.info. The twin's last line is
    # `echo "${GREEN}\u2713${NC} $checked ..."`, which lands on stdout, and
    # `rediacc_ci.log` writes every message to stderr by design. Both spellings are CHATTER to `scripts/lib/shadow-gate.ts`, so the differential would score the two as equivalent either way; that is exactly why it has to be got right by reading the twin rather than by watching the comparator.
    print(
        "\u2713 %d pattern-substitution control(s) prove their plant landed (%d bash, %d python); "
        "%d built by construction or planting nothing (exempt); the raw-substitution half of the "
        "python question belongs to check:ci-python-control-plants"
        % (checked, sh_checked, py_checked, sh_exempt + py_exempt)
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
    ctl = Controls("control-vacuity", floor=39, verbose=True)

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

    # -- the PYTHON arm's three predicates, both directions each ----------
    ctl.check("PY: a plant call registers", py_plants(['    m = plant(src, "a", "b")']), True)
    ctl.check("PY: plant_re registers too", py_plants(["    m = plant_re(src, r'a', 'b')"]), True)
    ctl.check(
        "MIRROR: an attribute access of the same name is not a harness call",
        py_plants(["    m = self.plant(src)"]),
        False,
    )
    ctl.check("MIRROR: a module that plants nothing is exempt", py_plants(["x = 1"]), False)
    ctl.check(
        "PROOF: the harness import with no local shadow resolves",
        py_plant_is_proven(["from rediacc_ci.controls import Controls, plant", "plant(a, b, c)"]),
        True,
    )
    ctl.check(
        "MIRROR: a plant with no harness import does not",
        py_plant_is_proven(["plant(a, b, c)"]),
        False,
    )
    # THE HALF A TOKEN COUNT CANNOT SEE, and the sibling gate's header names it as the false negative it would otherwise carry: the import is present AND a local definition shadows it, so every call goes somewhere that refuses nothing.
    ctl.check(
        "MIRROR: a LOCAL def of the same name shadows the harness",
        py_plant_is_proven(
            ["from rediacc_ci.controls import plant", "def plant(a, b):", "    return b"]
        ),
        False,
    )
    ctl.check(
        "STRIP: the harness import is removed and the plants stay",
        strip_harness_import(["from rediacc_ci.controls import plant", "plant(a, b, c)"]),
        ["plant(a, b, c)"],
    )

    # -- py_code_lines, the three removals --------------------------------
    ctl.check(
        "CODE: a comment naming a plant is prose",
        py_code_lines(["# plant(a, b, c)"]),
        [],
    )
    ctl.check(
        "CODE: a triple-quoted fixture defining a local plant is a fixture",
        py_code_lines(['_FIXTURE = """', "def plant(a, b):", '"""', "x = 1"]),
        ["x = 1"],
    )
    ctl.check(
        "CODE: a plant named inside a string literal is prose",
        py_code_lines(['    c.check("a plant(s) count", x)']),
        ['    c.check("", x)'],
    )
    ctl.check(
        "MIRROR: a real call beside a string literal survives the blanking",
        py_plants(py_code_lines(['    m = plant(src, "a", "b")  # noqa'])),
        True,
    )

    # -- the whole gate, over a fixture tree -------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        gate_dir = root / ".ci" / "scripts" / "quality"
        gate_dir.mkdir(parents=True)
        control_src = root / CONTROL_GATE
        control_src.parent.mkdir(parents=True, exist_ok=True)

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

        # The control gate the CONTROL block strips. It must carry BOTH the plants and the harness import, or the control cannot fire.
        control_src.write_text(
            _joined(
                "from rediacc_ci.controls import Controls, plant",
                "",
                "def selftest():",
                '    return plant(SRC, "per_kloc=25", "per_kloc=8")',
                "",
            ),
            encoding="utf-8",
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
        ctl.check("CONTROL: a compliant tree passes", run(), 0)

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

        # THE PYTHON HALF OF THE SAME PLANT: a module that plants while its `plant` resolves to nothing.
        unproven = gate_dir / "check_unproven.py"
        unproven.write_text('def selftest():\n    return plant(SRC, "a", "b")\n', encoding="utf-8")
        ctl.check("PLANT: a python plant that reaches no harness reds", run(), 1)
        unproven.unlink()

        # THE VACUITY CASE. Remove every substituting gate and every planting module and the corpus collapses; a gate that reported clean here would be reporting on nothing. The control source stays present but stops planting, which is the one state that empties the corpus without also tripping the missing-source refusal.
        (gate_dir / "check-good.sh").unlink()
        control_src.write_text("def selftest():\n    return 0\n", encoding="utf-8")
        ctl.check("VACUITY: a corpus that collapsed to zero reds", run(), 1)

        # And the control source going missing is its own refusal.
        control_src.unlink()
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
