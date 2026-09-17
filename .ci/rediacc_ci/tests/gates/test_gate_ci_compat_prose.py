"""Port of `.ci/scripts/test/gates/test-ci-compat-prose.sh`.

`.ci/scripts/security/check-commands.sh` must not read its own documentation as code.

WHY THIS EXISTS. Three detectors in this repo have flagged text that merely RESEMBLED the construct they forbid, all within one wave (2026-08-26): check-toolchain-pins.sh A6 read an `echo` line PRINTING the shellcheck directive as an INVOCATION of shellcheck; check-control-vacuity.sh read `sed 's/^/ /'`,
which indents a message for display, as a control built by pattern substitution;
and then it read a COMMENT about a substitution as the substitution itself.

check-commands.sh already skips comments and therefore did NOT make that mistake, but NOTHING PROVED the skip works, so deleting it would go unnoticed until a comment somewhere started failing CI. A detector that can flag its own documentation cannot be satisfied except by deleting the explanation, which is how a repo loses the record of why a rule exists.

The REAL script is driven against a constructed tree rather than its regexes being re-checked here: a copy of the predicate would pass while the shipped one rotted.

WHAT THIS CANNOT SEE: only the comment/code distinction for one representative banned command. It does not enumerate every entry in DISALLOWED.

THE BANNED TOKENS LIVE IN VARIABLES, and that is not squeamishness. Writing them in command position inside this file's own probe strings made check-commands.sh flag the GATE ITSELF: the token at the start of a probe line, and the other one after the `|` of an alternation, which its pattern reads as a pipeline. A gate that tests the comment/code distinction cannot be written in a
way that trips it. An assignment is not command position, so this form is invisible to the scanner
while still exercising the real thing. The same care applies here, which is why
the two names below are built as constants and interpolated.

WHAT THE PORT REIMPLEMENTS. The twin's live-tree case uses `grep -rlE '^[[:space:]]*#.*\\b(seq|mapfile)\\b' | wc -l`; this walks the same two directories in Python with the equivalent regex. The two agree because the pattern is anchored the same way (line start, optional whitespace, a `#`, then the word on word boundaries) and both count FILES rather than matches. Python's `re` is
used rather than shelling out to grep on purpose: the house note about ugrep's silent false zeros on an alternated anchor applies to exactly this shape, and a count of 0 here would trip the twin's own anti-vacuity floor rather than passing, but only on the bash side.

NO `xdist_group`. Every case builds its own `mktemp -d` root and runs the gate
with `cwd=` rather than chdir'ing this process; nothing global moves.
"""

import pathlib
import re
import shutil
import tempfile

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-ci-compat-prose.sh"

SUT = paths.from_root(".ci", "scripts", "security", "check-commands.sh")

# See the docstring: built rather than written, so this file is invisible to the scanner it exercises.
BANNED_SEQ = "s" + "eq"
BANNED_MAPFILE = "map" + "file"

# The anchor the control below cuts out. Named once so a rename reds the control loudly rather than making it a no-op.
SKIP_ANCHOR = "# Skip if it's in a comment"


def build_root(gate, work: pathlib.Path, probe: str) -> pathlib.Path:
    """A throwaway repo root whose ONLY shell script is the probe.

    The gate derives its root from its own path and scans `.ci` + `scripts`, so this exercises the shipped enumeration and the shipped skip logic rather than a re-implementation of either.
    """
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUT))
    root = pathlib.Path(tempfile.mkdtemp(dir=str(work)))
    (root / ".ci" / "scripts" / "security").mkdir(parents=True)
    shutil.copy2(SUT, root / ".ci" / "scripts" / "security" / "check-commands.sh")
    (root / ".ci" / "probe.sh").write_text(probe, encoding="utf-8")
    return root


def run_in(root: pathlib.Path) -> int:
    return harness.run(["./.ci/scripts/security/check-commands.sh"], cwd=root).rc


def test_a_banned_command_in_code_is_caught(gate):
    gate.log_test("the control that matters: a real banned command must FAIL")
    # If this does not fail, every other assertion here is vacuous: the gate would be passing everything.
    with harness.temp_dir() as work:
        probe = "#!/bin/bash\n%s 1 10\n" % BANNED_SEQ
        if run_in(build_root(gate, work, probe)) == 0:
            gate.log_fail("a real %s call was NOT caught; this gate proves nothing" % BANNED_SEQ)
    gate.log_pass("a banned command in code is caught")


def test_the_same_command_in_a_comment_is_ignored(gate):
    gate.log_test("the same command in a COMMENT must NOT fail")
    # THE PROBE MUST REACH THE SKIP BRANCH, and the obvious probe does not. check-commands.sh's outer scan requires the banned word to be immediately preceded by line-start whitespace, `|`, `&`, `;`, `$(` or `if `. In plain prose the word follows an ordinary letter, so the outer regex never matches and the skip branch is never consulted; such a probe passes identically
    # with the branch DELETED, measured exit 0 both ways. Putting the word
    # directly after a trigger character makes the outer scan match, so the only thing that can suppress it is the skip branch itself.
    with harness.temp_dir() as work:
        probe = "#!/bin/bash\n# equivalent to: cmd | %s 1 10\necho ok\n" % BANNED_SEQ
        if run_in(build_root(gate, work, probe)) != 0:
            gate.log_fail(
                "a banned command inside a COMMENT was flagged -- the gate now reads prose as code"
            )
    gate.log_pass("a comment whose banned word FOLLOWS a trigger char is not an invocation")


def test_control_the_probe_actually_reaches_the_skip_branch(gate):
    gate.log_test("CONTROL: delete the skip branch and the probe MUST flip")
    # The definitive control, and the one whose absence let a vacuous version of this file ship: copy the real gate, delete ONLY the comment-skip branch, and require the same probe to change its verdict. If it does not, the probe is not exercising the branch and every assertion above is decoration.
    with harness.temp_dir() as work:
        probe = "#!/bin/bash\n# equivalent to: cmd | %s 1 10\necho ok\n" % BANNED_SEQ
        root = build_root(gate, work, probe)
        copy = root / ".ci" / "scripts" / "security" / "check-commands.sh"
        rc_intact = run_in(root)

        # The twin plants this cut with an inline python heredoc. Same edit, same anchors: from the comment marker through the end of the `fi` that closes it.
        source = copy.read_text(encoding="utf-8")
        start = source.find(SKIP_ANCHOR)
        if start < 0:
            gate.log_fail(
                "could not plant the control: %r is not in %s, so the branch was renamed "
                "and this control would silently assert nothing"
                % (SKIP_ANCHOR, paths.relative_to_root(SUT))
            )
        end = source.index("fi\n", start) + 3
        copy.write_text(source[:start] + source[end:], encoding="utf-8")

        rc_cut = run_in(root)

        if rc_intact != 0:
            gate.log_fail(
                "the probe already fails WITH the skip branch present (rc=%d)" % rc_intact
            )
        if rc_cut == 0:
            gate.log_fail(
                "CONTROL DID NOT FIRE: deleting the comment-skip branch changed nothing, "
                "so the probe never reaches it"
            )
    gate.log_pass("probe reaches the branch: intact=%d, branch-deleted=%d" % (rc_intact, rc_cut))


def test_this_repos_own_explanations_survive(gate):
    gate.log_test("the real tree's own comments about banned commands stay clean")
    # WHAT THIS DOES AND DOES NOT PROVE. It guards against OVER-firing: the live tree must stay green while it genuinely documents banned commands in prose. It does NOT exercise the comment-skip branch, because none of those files mentions a banned command directly after a trigger char, so the outer scan never matches their comment lines. The control above is the only assertion
    # here that reaches the branch.
    pattern = re.compile(r"^[ \t]*#.*\b(%s|%s)\b" % (BANNED_SEQ, BANNED_MAPFILE), re.MULTILINE)
    documented = 0
    scanned = 0
    for directory in ("quality", "security"):
        base = paths.from_root(".ci", "scripts", directory)
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if pattern.search(text):
                documented += 1
    if scanned == 0:
        gate.log_fail(
            "the two scan roots hold no files at all, so the count below is not a "
            "measurement of anything and its green would mean nothing"
        )
    if documented < 1:
        gate.log_fail(
            "anti-vacuity: found no file documenting a banned command, so this proves nothing"
        )
    if harness.run([str(SUT)], cwd=paths.repo_root()).rc != 0:
        gate.log_fail("the live tree fails the gate; its own explanations are being read as code")
    gate.log_pass(
        "%d of %d file(s) document a banned command in prose; tree green (over-fire "
        "guard, NOT skip-branch coverage)" % (documented, scanned)
    )
