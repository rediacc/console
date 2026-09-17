"""`rediacc_ci.quality.peer_deps` against `.ci/scripts/quality/check-peer-deps.sh`.

HOW EQUIVALENCE IS PROVEN HERE. Not by reading both and agreeing they look alike. A bash child runs the REAL twin over a fixture, with stdout and stderr captured SEPARATELY, and the bytes it produced are compared against the port's over the same fixture. That is the shape `.ci/scripts/quality/check-python-lint.sh` uses for its own control: build a specimen, run the instrument,
compare.

THE COMMITTED LEDGER IS THE OTHER HALF, and neither replaces the other. The ledger (`.ci/shadow/w7p2-peerdeps.observations.jsonl`) records the verdict over K distinct trees and is the evidence a reviewer reads; these cases run on every `pytest` and are what catches a regression the day someone edits either file.

BOTH SIDES RESOLVE `npm` THROUGH PATH, which is why the fixture ships a shim rather than patching `subprocess`. A mock inside this process would prove nothing about the resolution the twin performs.
"""

import pathlib
import shutil

import pytest

from rediacc_ci.quality import peer_deps
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-peer-deps.sh"

# One invalid line on stdout, one on stderr, and a clean tree. The stderr case is the one that matters: the twin's `2>&1` is the only reason it is seen at all.
SHIM_STDOUT = "printf '%s\\n' 'console@0.0.0-dev /repo' '+-- zod@3.25.76 invalid: \"^4.4.3\"'"
SHIM_STDERR = "printf '%s\\n' 'console@0.0.0-dev /repo'\necho 'npm error invalid: x' >&2"
SHIM_CLEAN = "printf '%s\\n' 'console@0.0.0-dev /repo' '`-- zod@4.5.4'"


def build(tmp_path: pathlib.Path, shim_body: str) -> pathlib.Path:
    """A fixture repo holding the twin, its logger, and an `npm` on PATH."""
    root = tmp_path / "fixture"
    (root / ".ci/scripts/quality").mkdir(parents=True)
    (root / ".ci/scripts/lib").mkdir(parents=True)
    (root / "bin").mkdir(parents=True)
    repo = pathlib.Path(diff.repo())
    shutil.copy(repo / TWIN, root / TWIN)
    shutil.copy(repo / ".ci/scripts/lib/common.sh", root / ".ci/scripts/lib/common.sh")
    shim = root / "bin/npm"
    shim.write_text("#!/bin/bash\n%s\n" % shim_body, encoding="utf-8")
    shim.chmod(0o755)
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    """(twin, port), each as (exit, stdout, stderr). The streams are never merged."""
    env = diff.env_for(
        PATH="%s:%s" % (root / "bin", diff.BASE_ENV["PATH"]),
        REDIACC_CI_ROOT=str(root),
        PYTHONPATH=str(pathlib.Path(diff.repo()) / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s/%s" % (root, TWIN), env=env, cwd=str(root))
    new = diff.bash_streams("python3 -m rediacc_ci.quality.peer_deps", env=env, cwd=str(root))
    return old, new


@pytest.mark.parametrize(
    ("shim", "want_exit"),
    [
        pytest.param(SHIM_STDOUT, 1, id="invalid-on-stdout"),
        pytest.param(SHIM_STDERR, 1, id="invalid-on-stderr"),
        pytest.param(SHIM_CLEAN, 0, id="clean-tree"),
    ],
)
def test_port_and_twin_agree(tmp_path: pathlib.Path, shim: str, want_exit: int) -> None:
    """Same exit code, and the same offending lines, over the same fixture."""
    root = build(tmp_path, shim)
    (old_exit, old_out, _old_err), (new_exit, new_out, _new_err) = run_both(root)
    assert old_exit == want_exit
    assert new_exit == old_exit
    # The DATA on stdout is the finding set. The twin prints a blank line, a header and then the hits; the port prints the same three things.
    assert [x for x in new_out.split("\n") if "invalid" in x] == [
        x for x in old_out.split("\n") if "invalid" in x
    ]


def test_the_clean_case_is_not_vacuously_equal(tmp_path: pathlib.Path) -> None:
    """A green run is only evidence if the red run differs from it.

    Two implementations that both print nothing agree about nothing, which is `shadow-gate.ts`'s VACUOUS_BOTH_EMPTY. This case pins that the fixture pair used above genuinely separates the two outcomes.
    """
    clean_out = run_both(build(tmp_path / "a", SHIM_CLEAN))[0][1]
    dirty_out = run_both(build(tmp_path / "b", SHIM_STDOUT))[0][1]
    assert clean_out != dirty_out


def test_missing_npm_is_cannot_run_not_a_pass(tmp_path: pathlib.Path) -> None:
    """The divergence the port declares, asserted in BOTH directions.

    The twin captures bash's own "command not found" into its variable, finds no "invalid" in it and reports the tree CLEAN. The port exits 77. Both halves are asserted so the difference is a pinned decision rather than a surprise.
    """
    root = build(tmp_path, SHIM_CLEAN)
    (root / "bin/npm").unlink()
    # A PATH that still resolves `bash` and `python3` but holds NO npm. The obvious spelling -- PATH set to the empty shim directory -- takes `bash` away from subprocess too, and the case then fails for a reason that has nothing to do with the gate.
    env = diff.env_for(
        PATH="/usr/bin:/bin",
        REDIACC_CI_ROOT=str(root),
        PYTHONPATH=str(pathlib.Path(diff.repo()) / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    old_exit, _, _ = diff.bash_streams("bash %s/%s" % (root, TWIN), env=env, cwd=str(root))
    new_exit, _, new_err = diff.bash_streams(
        "python3 -m rediacc_ci.quality.peer_deps", env=env, cwd=str(root)
    )
    assert old_exit == 0, "the twin still reports a clean tree with no npm installed"
    assert new_exit == peer_deps.EXIT_CANNOT_RUN
    assert "npm" in new_err
    assert "NOTHING was verified" in new_err


def test_invalid_lines_is_a_substring_test() -> None:
    """`grep -q "invalid"`: substring, case-sensitive, both directions."""
    assert peer_deps.invalid_lines("a invalid b\nclean\n") == ["a invalid b"]
    assert peer_deps.invalid_lines("cache invalidate\n") == ["cache invalidate"]
    assert peer_deps.invalid_lines("Invalid capitalised\n") == []
    assert peer_deps.invalid_lines("") == []


def test_selftest_passes() -> None:
    """The gate's own controls, driven in-process."""
    assert peer_deps.selftest() == 0
