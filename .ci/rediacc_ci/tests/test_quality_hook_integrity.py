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

So all three heredocs are EXTRACTED from the twin and run as subprocesses over the same inputs, and compared. That is stronger than any hand-written expectation, because it fails when either side changes.
"""

import json
import pathlib
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.quality import hook_integrity as hi

TWIN = paths.from_root(".ci", "scripts", "quality", "check-hook-integrity.sh")


def _heredoc(marker: str, after: str) -> str:
    """The body of the first `<<'MARKER'` heredoc that follows `after`.

    THE OPENING IS NOT ALWAYS THE END OF ITS LINE. `scope_list` writes `<<'PY' 2>/dev/null`, so anchoring on `<<'PY'\n` skips it and finds `mkspec`'s heredoc instead -- which extracts a real program, runs cleanly, and answers a different question. The first version of this helper did exactly that and the comparison failed as though the twin disagreed.
    """
    body = TWIN.read_text(encoding="utf-8")
    anchor = body.index(after)
    start = body.index("<<'%s'" % marker, anchor)
    start = body.index("\n", start) + 1
    end = body.index("\n%s\n" % marker, start)
    return body[start:end]


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


def test_floorcheck_matches_the_twin_on_the_real_harness() -> None:
    """The declared folding harness itself, which is section C's actual subject."""
    root = paths.repo_root()
    sources = hi.scope_list(root / hi.SCOPE_REL, "case_sources")
    harnesses = [s for s in sources if hi.HARNESS_RE.search((root / s).read_text(encoding="utf-8"))]
    assert harnesses, sources
    for source in harnesses:
        text = (root / source).read_text(encoding="utf-8")
        assert hi.floorcheck(text) == _twin_floorcheck(str(root / source)), source


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
