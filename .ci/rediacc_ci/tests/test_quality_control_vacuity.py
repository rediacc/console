"""`rediacc_ci.quality.control_vacuity` against the grep pipeline it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger
`.ci/shadow/w7p2-control-vacuity.observations.jsonl` drives the whole gate over
five distinct trees carrying each verdict this check can reach. What a ledger
row cannot isolate is the CLASSIFIER, which is three chained greps whose answer
decides whether a sibling gate is judged at all:

    grep -vE '^[[:space:]]*#'                      strip comments
    grep -vE "sed [^&]*[[:punct:]]s[/@|#]\\^[/@|#]"  drop prefix substitutions
    grep -qE '\\$\\{NAME//|sed [^&]*[[:punct:]]s[/@|#]|sed -i'

A classifier that narrows moves gates from "checked" to "exempt" and the gate
still prints a tick. So the cases below run the REAL pipeline over the REAL gate
directory, file by file, and require the port to agree on every one.

THE ONE KNOWN SET DIFFERENCE, measured on this host and asserted below rather
than left as a hope: `grep` here is ugrep, whose `[[:punct:]]` is the Unicode
punctuation categories and excludes `$ + < = > ^ ` | ~`. The port uses the wider
POSIX set. `test_the_port_and_the_live_grep_agree_on_every_gate` is what proves
the difference is unobservable on the corpus that exists.
"""

import pathlib
import subprocess

from rediacc_ci import paths
from rediacc_ci.quality import control_vacuity as cv
from rediacc_ci.tests import differential as diff


def _joined(*rows: str) -> str:
    """`"\n".join(rows)` behind a call. The rows stay one per line.

    A helper rather than a literal join because ruff's FLY002 rewrites a join
    over a LITERAL list into an f-string, and a ten-line shell fixture written
    as one f-string is unreadable. Passing the rows as arguments keeps the
    fixture legible and gives the linter nothing static to fold.
    """
    return "\n".join(rows)


# The pipeline, verbatim from check-control-vacuity.sh:81-83.
PIPELINE = (
    "grep -vE '^[[:space:]]*#' \"$F\" | "
    'grep -vE "sed [^&]*[[:punct:]]s[/@|#]\\^[/@|#]" | '
    "grep -qE '\\$\\{[A-Za-z_][A-Za-z0-9_]*//|sed [^&]*[[:punct:]]s[/@|#]|sed -i'"
)

HAS_CONTROL_GREP = (
    'grep -qE "CONTROL DID NOT FIRE|control could not plant|CONTROL IS VACUOUS|'
    'control_must_fail|^control\\(\\)" "$F"'
)


def _bash_true(script: str, path: pathlib.Path) -> bool:
    """Run a `grep -q` shell fragment against `path`; True when it exits 0."""
    code, out, err = diff.bash_streams('F="%s"; %s' % (path, script))
    assert err == "", err
    assert code in (0, 1), (code, out, err)
    return code == 0


def _gate_files() -> list[pathlib.Path]:
    return sorted((paths.repo_root() / ".ci" / "scripts" / "quality").glob("check-*.sh"))


def test_the_corpus_is_not_empty() -> None:
    """ZERO INPUTS IS A FAILURE. Every comparison below is vacuous if the glob
    stops matching, and a vacuous comparison passes silently."""
    assert len(_gate_files()) >= 50, "the gate directory collapsed; every case below proves nothing"


def test_the_port_and_the_live_grep_agree_on_every_gate() -> None:
    """`builds_by_substitution` over the whole real gate directory.

    This is the assertion that makes the POSIX-versus-ugrep `[[:punct:]]`
    difference safe to carry: if a gate ever contains a shape where the two
    readings disagree, this fails by name instead of the gate quietly moving
    one file from checked to exempt.
    """
    disagreements = []
    for path in _gate_files():
        want = _bash_true(PIPELINE, path)
        got = cv.builds_by_substitution(cv.read_lines(path))
        if want != got:
            disagreements.append((path.name, want, got))
    assert disagreements == [], disagreements


def test_has_control_agrees_with_the_live_grep_on_every_gate() -> None:
    disagreements = []
    for path in _gate_files():
        want = _bash_true(HAS_CONTROL_GREP, path)
        got = cv.has_control(cv.read_lines(path))
        if want != got:
            disagreements.append((path.name, want, got))
    assert disagreements == [], disagreements


def test_both_classes_are_non_empty_across_the_real_corpus() -> None:
    """A classifier that answered "yes" to everything, or "no" to everything,
    would pass both comparisons above only if the corpus happened to be
    uniform. It is not, and this says so with numbers."""
    substituting = [p.name for p in _gate_files() if cv.builds_by_substitution(cv.read_lines(p))]
    controlled = [p.name for p in _gate_files() if cv.has_control(cv.read_lines(p))]
    assert len(substituting) >= 3, substituting
    assert len(controlled) >= 5, controlled
    assert len(substituting) < len(_gate_files()), "everything classified as substituting"


def test_strip_guard_matches_the_twins_sed(tmp_path: pathlib.Path) -> None:
    """`sed '/<guard>/,+2d'` is a RANGE. Compared against the real sed, because
    the two plausible mis-readings (delete only the matching line; stop after
    the first range) both make the CONTROL easier to pass."""
    body = _joined(
        "keep 1",
        'if [[ "$MUTANT" == "$FN" ]]; then',
        "  fail x",
        "fi",
        "keep 2",
        'if [[ "$MUTANT" == "$FN" ]]; then',
        "  fail y",
        "fi",
        "keep 3",
        "",
    )
    target = tmp_path / "gate.sh"
    target.write_text(body, encoding="utf-8")
    code, out, err = diff.bash_streams(
        'sed \'/\\[\\[ "\\$MUTANT" == "\\$FN" \\]\\]/,+2d\' "%s"' % target
    )
    assert (code, err) == (0, ""), err
    assert cv.strip_guard(cv.read_lines(target)) == [line for line in out.split("\n") if line != ""]


def test_strip_guard_on_the_real_control_source_keeps_its_substitution() -> None:
    """The CONTROL's precondition, asserted directly: the stripped copy must
    still carry a substitution, or the control proves nothing and the gate says
    CONTROL IS VACUOUS. That branch firing on the real tree would be a finding
    about check-review-turn-capacity.sh, not about the port."""
    source = paths.repo_root() / ".ci" / "scripts" / "quality" / cv.CONTROL_GATE
    assert source.is_file(), "%s moved; retarget the control in BOTH implementations" % source
    stripped = cv.strip_guard(cv.read_lines(source))
    assert any(cv.CONTROL_STILL_SUBSTITUTES.search(line) for line in stripped)
    assert not cv.proves_plant_landed(stripped), "the CONTROL cannot fire; it proves nothing"


def test_prefix_substitutions_are_exempt_in_both_implementations(tmp_path: pathlib.Path) -> None:
    """The 2026-08-26 false positives, as fixtures. `s/^/.../` always matches,
    so it can never silently produce an identical copy."""
    for body in (
        "echo \"$hits\" | sed 's/^/         /'\n",
        "seq 1 5 | sed 's/^/echo /'\n",
    ):
        target = tmp_path / "probe.sh"
        target.write_text(body, encoding="utf-8")
        assert _bash_true(PIPELINE, target) is False, body
        assert cv.builds_by_substitution(cv.read_lines(target)) is False, body


def test_a_substitution_in_a_comment_is_prose_in_both(tmp_path: pathlib.Path) -> None:
    """The other 2026-08-26 false positive: a gate that documents the construct
    it avoids must not be flagged for the documentation."""
    target = tmp_path / "probe.sh"
    target.write_text("# we avoid ${SRC//needle/repl} here\necho hi\n", encoding="utf-8")
    assert _bash_true(PIPELINE, target) is False
    assert cv.builds_by_substitution(cv.read_lines(target)) is False


def test_all_three_substitution_shapes_register_in_both(tmp_path: pathlib.Path) -> None:
    """Including `sed -i "$expr"`, whose absence "mis-exempted the two gates
    that motivated this check"."""
    for body in (
        'MUTANT="${SRC//needle/repl}"\n',
        'sed \'s/needle/repl/\' "$SRC" >"$TMP/broken.sh"\n',
        'sed -i "$expr" "$TMP/broken.sh"\n',
    ):
        target = tmp_path / "probe.sh"
        target.write_text(body, encoding="utf-8")
        assert _bash_true(PIPELINE, target) is True, body
        assert cv.builds_by_substitution(cv.read_lines(target)) is True, body


def test_selftest_is_green() -> None:
    assert cv.selftest() == 0


def test_the_real_tree_passes_and_the_two_implementations_print_the_same_bytes() -> None:
    """Byte comparison on the real tree, both streams, kept SEPARATE.

    Not a substitute for the ledger: this is one tree, and one tree is one
    observation (`scripts/lib/shadow-gate.ts`, invariant 5). It is here because
    the twin's output is short enough for a byte comparison to be meaningful,
    and a byte comparison catches a moved stream that a finding-set comparison
    calls chatter and ignores.
    """
    root = str(paths.repo_root())
    old = subprocess.run(
        ["bash", ".ci/scripts/quality/check-control-vacuity.sh"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    new = subprocess.run(
        ["python3", "-m", "rediacc_ci.quality.control_vacuity"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={**diff.BASE_ENV, "PYTHONPATH": ".ci", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert old.returncode == new.returncode == 0, (old.stderr, new.stderr)
    assert old.stdout == new.stdout
    assert old.stderr == new.stderr
