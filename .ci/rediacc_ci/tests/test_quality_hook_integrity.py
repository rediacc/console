"""`rediacc_ci.quality.hook_integrity` against the twin's own embedded readers.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-hook-integrity.observations.jsonl` drives the whole gate over five distinct trees: a guard on disk the inventory does not list, a baselined guard whose file is gone, a guard newly missing both directions, an empty scope list, and a harness folding an external count with no minimum. What a ledger row cannot isolate is
that this gate's three readers were ALREADY Python, embedded as heredocs, and every one of them has a documented history of narrowing silently:

  * `covmap` missed the pre-edit and pre-ask chains entirely for months, and
    counted only literal `check N <guard>` calls, so two well-covered guards sat
    in the coverage baseline as gaps.
  * `floorcheck` reported a correctly floored fold as unfloored until its window
    included the fold line, and reported five zero-count refusals as defects
    until they were admitted as floors.
  * `scope_list` is the thing standing between a malformed data file and a gate
    that audits nothing and exits 0.

So all three heredocs are RUN as subprocesses over the same inputs, and compared. That is stronger than any hand-written expectation, because it fails when either side changes.

WHERE THE THREE PROGRAMS NOW COME FROM. W7 P5 batch G2 deleted `.ci/scripts/quality/check-hook-integrity.sh` once the ledger held, and each heredoc was recorded first: `goldens/hook-integrity/` holds the three programs as the extractor read them out of the tracked script on its last day in the tree, headed with the blob sha, so `git cat-file -p <sha>` still yields the file they
were cut from. THEY ARE STILL EXECUTED, over the same live inputs as before. That is the half that could not have been frozen even in principle: two of the comparisons below run over the REAL tree, whose guard inventory changes with every guard added, so a recording of their OUTPUT would have gone stale the same week. A recording of the PROGRAM does not.
"""

import json
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import hook_integrity as hi
from rediacc_ci.tests import frozen

SLUG = "hook-integrity"

# marker + anchor -> the golden holding that heredoc's recorded bytes. THE OPENING WAS NOT ALWAYS THE END OF ITS LINE: `scope_list` wrote `<<'PY' 2>/dev/null`, so an extractor anchoring on `<<'PY'\n` skipped it and found `mkspec`'s heredoc instead -- a real program that ran cleanly and answered a different question. The first version of the extractor did exactly that and the
# comparison failed as though the twin disagreed. The three names below are what
# that extractor finally returned, which is why the anchors survive here as keys.
HEREDOCS = {
    ("PY", "covmap() {"): "the-covmap-reader",
    ("FLOORPY", "floorcheck() {"): "the-floorcheck-reader",
    ("PY", "scope_list() {"): "the-scope-list-reader",
}


def _heredoc(marker: str, after: str) -> str:
    """One of the twin's embedded readers, as it was recorded."""
    text = frozen.read(SLUG, HEREDOCS[(marker, after)])
    exit_line, rest = text.split("\n", 1)
    assert exit_line == "exit: 0", "%s: the recorded extraction failed" % after
    return rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)[0].removesuffix("\n")


def _run_python(program: str, args: list[str], stdin: str = "") -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-", *args],
        input=(program + "\n").encode("utf-8") if not stdin else program.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    return (
        proc.returncode,
        proc.stdout.decode("utf-8"),
        proc.stderr.decode("utf-8"),
    )


def _twin_covmap(spec_path: str) -> list[tuple[str, int, int]]:
    """The twin's `covmap` heredoc, run over a spec file."""
    program = _heredoc("PY", "covmap() {")
    code, out, err = _run_python(program, [spec_path])
    assert code == 0, err
    rows = []
    for line in out.split("\n"):
        if line == "":
            continue
        key, block, allow = line.rsplit(" ", 2)
        rows.append((key, int(block), int(allow)))
    return rows


def _twin_floorcheck(path: str) -> list[int]:
    """The twin's `floorcheck` heredoc, run over a file."""
    program = _heredoc("FLOORPY", "floorcheck() {")
    code, out, err = _run_python(program, [path])
    assert code == 0, err
    return [int(line) for line in out.split("\n") if line != ""]


def _twin_scope(path: str, key: str) -> tuple[int, list[str]]:
    """The twin's `scope_list` heredoc. Returns (exit status, lines)."""
    program = _heredoc("PY", "scope_list() {")
    code, out, _err = _run_python(program, [path, key])
    return code, [line for line in out.split("\n") if line != ""]


def _spec_file(tmp_path: pathlib.Path, spec: dict) -> str:
    target = tmp_path / "spec.json"
    target.write_text(json.dumps(spec), encoding="utf-8")
    return str(target)


def test_covmap_matches_the_twin_on_the_fixture_tree(tmp_path: pathlib.Path) -> None:
    """The twin's own control fixture: both directions, block-only, check_out, helper."""
    hooks = hi.build_fixture_hooks(tmp_path)
    spec = hi.mkspec(str(hooks / "hooks"), [str(hooks / "suite.sh")], ["pre-bash", "pre-edit"])
    assert hi.covmap(spec) == _twin_covmap(_spec_file(tmp_path, spec))


def test_covmap_matches_the_twin_with_an_uncovered_guard_and_a_test_file(
    tmp_path: pathlib.Path,
) -> None:
    """The negative control and the dedicated-test-file rule, in one comparison.

    The uncovered guard is the one that matters: a reader that simply says yes to everything passes every positive case above.
    """
    hooks = hi.build_fixture_hooks(tmp_path)
    (hooks / "hooks" / "pre-bash" / "block-fixture-uncovered.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    (hooks / "hooks" / "pre-bash" / "test-block-fixture-blockonly.py").write_text(
        "", encoding="utf-8"
    )
    spec = hi.mkspec(str(hooks / "hooks"), [str(hooks / "suite.sh")], ["pre-bash", "pre-edit"])
    got = hi.covmap(spec)
    assert got == _twin_covmap(_spec_file(tmp_path, spec))
    assert ("pre-bash/block-fixture-uncovered.sh", 0, 0) in got


def test_covmap_matches_the_twin_on_a_python_ported_guard(tmp_path: pathlib.Path) -> None:
    """`block_ported.py`: hyphen to underscore, which is what a port produces.

    A reader anchored on `block-` inventories it and never asks it for a direction, which is a silent hole opened by a correct port.
    """
    hooks = hi.build_fixture_hooks(tmp_path)
    (hooks / "hooks" / "pre-bash" / "block_ported.py").write_text("", encoding="utf-8")
    spec = hi.mkspec(str(hooks / "hooks"), [str(hooks / "suite.sh")], ["pre-bash", "pre-edit"])
    got = hi.covmap(spec)
    assert got == _twin_covmap(_spec_file(tmp_path, spec))
    assert any(key == "pre-bash/block_ported.py" for key, _b, _a in got)


def test_covmap_matches_the_twin_on_the_real_tree(tmp_path: pathlib.Path) -> None:
    """The live corpus, and a floor under it: a zero-row comparison proves nothing."""
    root = paths.repo_root()
    scope = root / hi.SCOPE_REL
    spec = hi.mkspec(
        str(root),
        hi.scope_list(scope, "case_sources"),
        hi.scope_list(scope, "guard_dirs"),
    )
    got = hi.covmap(spec)
    assert len(got) >= 30, len(got)
    assert got == _twin_covmap(_spec_file(tmp_path, spec))


def test_floorcheck_matches_the_twin_on_every_spelling(tmp_path: pathlib.Path) -> None:
    """Four fixtures the twin carries, plus the out-of-window case."""
    cases = {
        "floored": hi.FIXTURE_FLOORED,
        "literal": hi.FIXTURE_FLOORED_LITERAL,
        "zero": hi.FIXTURE_FLOORED_ZERO,
        "unfloored": hi.FIXTURE_UNFLOORED,
        "single": "PASS=$((PASS + 1))\n",
        "far": '[ "$n" -lt "$floor" ]\n' + "x\n" * 12 + "PASS=$((PASS + n))\n",
    }
    for label, text in cases.items():
        target = tmp_path / ("%s.sh" % label)
        target.write_text(text, encoding="utf-8")
        assert hi.floorcheck(text) == _twin_floorcheck(str(target)), label


HARNESS_RECORDING = (
    "rediacc_ci",
    "tests",
    "goldens",
    "claude-hooks",
    "test-hooks.sh.golden",
)


def test_floorcheck_matches_the_twin_on_the_real_harness() -> None:
    """The bash folding harness itself, read from the recording that replaced it.

    THE SUBJECT IS A GOLDEN BECAUSE THE SUBJECT WAS DELETED. `.claude/hooks/test-hooks.sh` was section C's only bash case source; when it was ported to pytest this test's `assert harnesses` went empty and the comparison would have been retired or, worse, left to run over the Python sources, where both implementations return `[]` and agree about nothing. The harness's exact
    bytes are kept at the path below, headed with its blob sha, so the two readers are still compared over the 2,779 lines they were written against -- eight real folds, each with a real floor -- rather than over a file with no folds in it.

    THE HEADER IS NOT STRIPPED HERE, deliberately: both sides read the SAME file, so the one-line offset is common to both and equality is unaffected. Stripping it would mean writing a temporary copy, which is a second thing to be wrong about.
    """
    recording = paths.from_root(".ci", *HARNESS_RECORDING)
    assert recording.is_file(), (
        "%s is missing, so this differential would have no subject and would pass by "
        "comparing nothing" % recording
    )
    text = recording.read_text(encoding="utf-8")
    assert hi.HARNESS_RE.search(text), (
        "the recording no longer carries an external PASS fold, so it is not the harness "
        "this comparison was written for"
    )
    found = hi.floorcheck(text)
    assert found == _twin_floorcheck(str(recording)), recording
    assert found == [], (
        "the recorded harness floored every fold on its last day; a non-empty result here "
        "means the recording was altered, not that a floor was lost: %s" % found
    )


def test_scope_list_matches_the_twin_on_every_malformed_shape(
    tmp_path: pathlib.Path,
) -> None:
    """The refusal, which is what stops a malformed data file becoming a green gate."""
    scope = tmp_path / "scope.json"
    scope.write_text(
        json.dumps({"ok": ["a", "b"], "empty": [], "notlist": "a", "blank": [""], "num": [1]}),
        encoding="utf-8",
    )
    code, lines = _twin_scope(str(scope), "ok")
    assert code == 0
    assert hi.scope_list(scope, "ok") == lines == ["a", "b"]

    for key in ("empty", "notlist", "blank", "num", "absent"):
        code, _lines = _twin_scope(str(scope), key)
        assert code != 0, key
        try:
            hi.scope_list(scope, key)
        except hi.ScopeError:
            continue
        raise AssertionError("scope_list accepted %r" % key)


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, over fixtures built by construction."""
    assert hi.selftest() == 0


def test_every_heredoc_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a reader whose golden vanished would never be run, and a golden nothing reads is a recording of a comparison that stopped happening."""
    frozen.assert_corpus(SLUG, set(HEREDOCS.values()))


def test_the_recorded_readers_are_programs_and_not_empty_captures() -> None:
    """An extraction that had captured nothing would make all three comparisons vacuous.

    Each recording is asserted to be a runnable program that names the thing it reads, so a golden written from a failed slice reds here rather than turning every comparison below into a subprocess that prints nothing and agrees with a port that also printed nothing.
    """
    covmap = _heredoc("PY", "covmap() {")
    floorcheck = _heredoc("FLOORPY", "floorcheck() {")
    scope = _heredoc("PY", "scope_list() {")
    assert 'sources, dirs = spec["sources"], spec["dirs"]' in covmap
    assert len(covmap.split("\n")) > 30
    assert "import re, sys" in floorcheck
    assert len(floorcheck.split("\n")) > 15
    assert "sys.argv[2]" in scope
    assert scope.rstrip().endswith("print(x)")


def test_planted_defect_is_caught_by_the_recorded_reader(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Say yes to every guard, in the recorded reader.

    A coverage reader that credits both directions unconditionally is the shape this gate's own history records twice, and it passes every positive fixture. The mutation is applied to a LOCAL copy of the recorded program; the golden on disk is never rewritten.
    """
    hooks = hi.build_fixture_hooks(tmp_path)
    (hooks / "hooks" / "pre-bash" / "block-fixture-uncovered.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    spec = hi.mkspec(str(hooks / "hooks"), [str(hooks / "suite.sh")], ["pre-bash", "pre-edit"])
    spec_path = _spec_file(tmp_path, spec)

    program = _heredoc("PY", "covmap() {")
    anchor = '        b, a = counts.get("%s/%s" % (seg, name), (0, 0))\n'
    assert program.count(anchor) == 1, "the plant's anchor moved"
    broken = program.replace(anchor, "        b, a = (1, 1)\n")
    assert broken != program

    code, out, err = _run_python(broken, [spec_path])
    assert code == 0, err
    assert "pre-bash/block-fixture-uncovered.sh 1 1" in out, "the plant did not land"
    # The port, and the unmutated recording, both still call that guard uncovered.
    assert ("pre-bash/block-fixture-uncovered.sh", 0, 0) in hi.covmap(spec)
    assert hi.covmap(spec) == _twin_covmap(spec_path)
    with pytest.raises(AssertionError):
        assert "pre-bash/block-fixture-uncovered.sh 1 1" in _run_python(program, [spec_path])[1]
