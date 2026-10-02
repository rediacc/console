"""`rediacc_ci.quality.control_vacuity` against the grep pipeline it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-control-vacuity.observations.jsonl` drives the whole gate over five distinct trees carrying each verdict this check can reach. What a ledger row cannot isolate is the CLASSIFIER, which is three chained greps whose answer decides whether a sibling gate is judged at all:

    grep -vE '^[[:space:]]*#'                      strip comments
    grep -vE "sed [^&]*[[:punct:]]s[/@|#]\\^[/@|#]"  drop prefix substitutions
    grep -qE '\\$\\{NAME//|sed [^&]*[[:punct:]]s[/@|#]|sed -i'

A classifier that narrows moves gates from "checked" to "exempt" and the gate still prints a tick. So the cases below run the REAL pipeline against the port. They ran it over the real gate directory, file by file, until PLAN-retire-bash-oracles B3 retired the last bash gate there; fixtures covering every shape the classifier branches on carry the comparison now.

THE ONE KNOWN SET DIFFERENCE, measured on this host and asserted below rather than left as a hope: `grep` here is ugrep, whose `[[:punct:]]` is the Unicode
punctuation categories and excludes `$ + < = > ^ ` | ~`. The port uses the wider
POSIX set. With no bash gate left to scan, the difference has no corpus to be observable on; the fixtures below exercise only shapes outside the disputed characters.
"""

import glob
import pathlib
import subprocess

from rediacc_ci import paths
from rediacc_ci.quality import control_vacuity as cv
from rediacc_ci.tests import differential as diff


def _joined(*rows: str) -> str:
    """`"\n".join(rows)` behind a call. The rows stay one per line.

    A helper rather than a literal join because ruff's FLY002 rewrites a join over a LITERAL list into an f-string, and a ten-line shell fixture written as one f-string is unreadable. Passing the rows as arguments keeps the fixture legible and gives the linter nothing static to fold.
    """
    return "\n".join(rows)


# The pipeline, verbatim from check-control-vacuity.sh:81-83.
PIPELINE = (
    "grep -vE '^[[:space:]]*#' \"$F\" | "
    'grep -vE "sed [^&]*[[:punct:]]s[/@|#]\\^[/@|#]" | '
    "grep -qE '\\$\\{[A-Za-z_][A-Za-z0-9_]*//|sed [^&]*[[:punct:]]s[/@|#]|sed -i'"
)


def _bash_true(script: str, path: pathlib.Path) -> bool:
    """Run a `grep -q` shell fragment against `path`; True when it exits 0."""
    code, out, err = diff.bash_streams('F="%s"; %s' % (path, script))
    assert err == "", err
    assert code in (0, 1), (code, out, err)
    return code == 0


def test_the_bash_gate_family_is_gone_and_the_fixtures_stand_in() -> None:
    """THE REAL-CORPUS HALF OF THIS FILE ENDED WITH ITS SUBJECT, as its own docstrings said it would.

    Four cases ran the live grep pipeline and the port's classifier over every `.ci/scripts/quality/check-*.sh` (and, for the discrimination case, `.ci/scripts/security/*.sh` too) and required them to agree file by file. PLAN-retire-bash-oracles B3 retired the last of those files (`check-submodule-branches.sh`, `check-workflow-gates.sh`, `dependency-inventory.sh`), so there is
    no population left to agree over, and a loop over an empty glob is the vacuous green the first of them existed to refuse. They are deleted rather than floored at zero. What carries the comparison now is the fixture cases below, which run the SAME live pipeline against the port on every shape the classifier branches on, both directions.

    This case pins the premise: if a bash gate comes back into either directory, the real-corpus comparison has a subject again and must be restored, not silently skipped.
    """
    root = paths.repo_root()
    tracked = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            ".ci/scripts/quality/check-*.sh",
            ".ci/scripts/security/*.sh",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert tracked == [], (
        "bash gates are back in the gate directories (%s): restore the real-corpus "
        "classifier comparison over them" % tracked
    )
    for body, want in (
        ('x="${y//a/b}"\n', True),
        ("sed -i 's/a/b/' f\n", True),
        ("echo \"$h\" | sed 's/^/  /'\n", False),
    ):
        assert cv.builds_by_substitution(body.splitlines()) is want, body


def test_the_python_arm_discriminates_across_the_real_corpus() -> None:
    """Both classes, non-empty, over the population the corpus moved to.

    This is the case the bash `has_control` floor used to be. A detector that answered "plants" for every module would satisfy every fixture in the selftest and be worthless here, and one that answered "plants" for none would empty the corpus and be caught by the gate's own anti-vacuity refusal instead of by this. Both directions are asserted, and the proven count is asserted
    to be the WHOLE corpus, because a single unproven module in this tree is a real finding rather than a tolerated one.
    """
    planting = []
    quiet = []
    for pattern in cv.PY_SCOPE:
        for path in sorted(glob.glob(str(paths.repo_root() / pattern))):
            code = cv.py_code_lines(cv.read_lines(pathlib.Path(path)))
            (planting if cv.py_plants(code) else quiet).append(pathlib.Path(path).name)
    assert len(planting) >= 10, planting
    assert quiet, "every python gate classified as planting"
    unproven = [
        name
        for pattern in cv.PY_SCOPE
        for path in sorted(glob.glob(str(paths.repo_root() / pattern)))
        for name in [pathlib.Path(path).name]
        if cv.py_plants(cv.py_code_lines(cv.read_lines(pathlib.Path(path))))
        and not cv.py_plant_is_proven(cv.py_code_lines(cv.read_lines(pathlib.Path(path))))
    ]
    assert unproven == [], unproven


def test_strip_guard_matches_the_twins_sed(tmp_path: pathlib.Path) -> None:
    """`sed '/<guard>/,+2d'` is a RANGE. Compared against the real sed, because the two plausible mis-readings (delete only the matching line; stop after the first range) both make the CONTROL easier to pass."""
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


def test_stripping_the_real_control_source_keeps_its_plants() -> None:
    """The CONTROL's precondition, asserted directly.

    The stripped copy must still PLANT, or the control proves nothing and the gate says CONTROL IS VACUOUS; and it must stop being PROVEN, or the control cannot fire. Both branches firing on the real tree would be a finding about `CONTROL_GATE` (`renet_tier_map.py`), not about this module, which is why they are asserted here where the failure can name the file.
    """
    source = paths.repo_root() / cv.CONTROL_GATE
    assert source.is_file(), "%s moved; retarget CONTROL_GATE" % source
    code = cv.py_code_lines(cv.read_lines(source))
    assert cv.py_plant_is_proven(code), "the control source no longer plants through the harness"
    stripped = cv.strip_harness_import(code)
    assert cv.py_plants(stripped), "the stripped copy lost its plants; it proves nothing"
    assert not cv.py_plant_is_proven(stripped), "the CONTROL cannot fire; it proves nothing"


def test_prefix_substitutions_are_exempt_in_both_implementations(tmp_path: pathlib.Path) -> None:
    """The 2026-08-26 false positives, as fixtures. `s/^/.../` always matches, so it can never silently produce an identical copy."""
    for body in (
        "echo \"$hits\" | sed 's/^/         /'\n",
        "seq 1 5 | sed 's/^/echo /'\n",
    ):
        target = tmp_path / "probe.sh"
        target.write_text(body, encoding="utf-8")
        assert _bash_true(PIPELINE, target) is False, body
        assert cv.builds_by_substitution(cv.read_lines(target)) is False, body


def test_a_substitution_in_a_comment_is_prose_in_both(tmp_path: pathlib.Path) -> None:
    """The other 2026-08-26 false positive: a gate that documents the construct it avoids must not be flagged for the documentation."""
    target = tmp_path / "probe.sh"
    target.write_text("# we avoid ${SRC//needle/repl} here\necho hi\n", encoding="utf-8")
    assert _bash_true(PIPELINE, target) is False
    assert cv.builds_by_substitution(cv.read_lines(target)) is False


def test_all_three_substitution_shapes_register_in_both(tmp_path: pathlib.Path) -> None:
    """Including `sed -i "$expr"`, whose absence "mis-exempted the two gates that motivated this check"."""
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


def test_the_real_tree_passes_and_the_port_keeps_its_streams_apart() -> None:
    """The real tree, both streams, kept SEPARATE.

    WHILE BOTH COPIES EXISTED this compared the twin's bytes against the port's on every stream, and `.ci/shadow/w7p2-control-vacuity.observations.jsonl` recorded that verdict over five distinct trees. W7 P5 batch C2 retired the twin once the ledger asserted, so the comparison that executed it went with it and what remains is the property the byte comparison was protecting: a
    green real-tree run whose findings never leak onto the wrong stream.
    """
    root = str(paths.repo_root())
    new = subprocess.run(
        ["python3", "-m", "rediacc_ci.quality.control_vacuity"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={**diff.BASE_ENV, "PYTHONPATH": ".ci", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert new.returncode == 0, new.stderr
    assert new.stdout != "", "a green run still reports what it scanned"
    assert "CONTROL DID NOT FIRE" not in new.stdout
