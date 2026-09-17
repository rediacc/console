"""`rediacc_ci.quality.script_exec_bit` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-script-exec-bit.sh` over a git fixture with stdout and stderr captured SEPARATELY, and its bytes are compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-script-exec-bit.observations.jsonl`.

THE FIXTURE IS A REAL GIT REPOSITORY, and that is not incidental: this gate reads the INDEX mode, not the filesystem mode, because "the index is what CI checks out". A fixture built as a plain directory would make both implementations enumerate zero paths and agree perfectly about nothing, which is the both-empty trap `scripts/lib/shadow-gate.ts` names as rule 2.

BOTH DIRECTIONS, EVERY CASE. The corpus carries an offender (must fire), an executable script (must stay quiet), a reference inside a comment (must stay quiet), and a `../decoy.sh` in a subdirectory (must stay quiet, and is the case whose first version in the twin could not fail because the correct and the broken behaviour deduped to the same set).

WHAT IS ALSO ASSERTED HERE AND NOWHERE ELSE: that the port's REFUSAL status is 2 and not 1. The twin distinguishes "the control could not fire" from "the tree has offenders", and a port that collapsed them would make an unrunnable gate read as a failing tree, which is the direction that gets a gate deleted.
"""

import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci.quality import script_exec_bit as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-script-exec-bit.sh"
MODULE = "script_exec_bit"


def build(tmp_path: pathlib.Path, files: dict[str, tuple[str, int]]) -> pathlib.Path:
    """A sealed git specimen holding BOTH implementations plus `files`.

    `files` maps a repo-relative path to (text, octal mode). The MODE is the subject of this gate, so it is explicit at every call site rather than inherited from the umask.
    """
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    for rel, (text, mode) in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        target.chmod(mode)
    for args in (
        ["init", "-q", "-b", "main", "."],
        ["config", "user.email", "gate@example.invalid"],
        ["config", "user.name", "test"],
        ["add", "-A"],
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "specimen"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    """Both implementations over one specimen, streams never merged."""
    old = diff.bash_streams("bash %s" % TWIN, cwd=str(root))
    new = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s" % MODULE,
        cwd=str(root),
    )
    return old, new


CASES = [
    (
        "one non-executable script invoked from a workflow",
        {"alpha.sh": ("#!/bin/bash\necho a\n", 0o644), "caller.yml": ("run: ./alpha.sh\n", 0o644)},
        1,
    ),
    (
        # THE NEGATIVE HALF. Same shape, mode 755, must go quiet. Without this a detector that flags every referenced script passes the case above.
        "the same script committed executable is not reported",
        {"alpha.sh": ("#!/bin/bash\necho a\n", 0o755), "caller.yml": ("run: ./alpha.sh\n", 0o644)},
        0,
    ),
    (
        "a nested reference resolves against the referring file",
        {
            "tools/beta.sh": ("#!/bin/bash\necho b\n", 0o644),
            "tools/driver.sh": ("#!/bin/bash\nbash ./beta.sh\n", 0o755),
        },
        1,
    ),
    (
        # DOCUMENTATION IS NOT AN INVOCATION. Both false positives the twin was written for are this shape.
        "a reference inside a comment is documentation, not an invocation",
        {"eta.sh": ("#!/bin/bash\necho e\n", 0o644), "caller.yml": ("# Usage: ./eta.sh\n", 0o644)},
        0,
    ),
    (
        # THE ANCHOR CONTROL. `../iota.sh` from inside sub/ must NOT be read as `./iota.sh` relative to sub/.
        "a parent-relative reference is not a local one",
        {
            "sub/iota.sh": ("#!/bin/bash\necho i\n", 0o644),
            "sub/parentref.yml": ("run: ../iota.sh\n", 0o644),
        },
        0,
    ),
    (
        "a markdown reference is in scope",
        {"kappa.sh": ("#!/bin/bash\necho k\n", 0o644), "README.md": ("Run `./kappa.sh`.\n", 0o644)},
        1,
    ),
    (
        # AN UNTRACKED TARGET IS NOT OURS. The reference names a path git does not know, so no mode exists and nothing is reported. `git add -A` picks up every file written here, so the untracked case is expressed by naming a path that was never written at all.
        "a reference to a path git does not track is skipped",
        {"caller.yml": ("run: ./nowhere.sh\n", 0o644)},
        0,
    ),
]


@pytest.mark.parametrize(
    ("files", "want_exit"),
    [(c[1], c[2]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_differential(tmp_path, files, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, files)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == want_exit, "the twin's verdict moved: %s%s" % (old_out, old_err)
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


def test_colour_is_unconditional_on_both_sides():
    """The twin colours with no tty test, so the port must too.

    This is the ONE place the difference would be invisible: `rediacc_ci.log` decides colour by `isatty`, and a port that used it would emit no escapes off a terminal. Every differential above runs off a pipe, so it would agree with a twin that also emitted none. The twin emits them ANYWAY, which is why this asserts the escape count is non-zero rather than merely equal.
    """
    assert gate.RED.startswith("\033[")
    assert gate.RED == "\033[31m", "the twin uses 31m, not common.sh's 0;31m"
    assert gate.GREEN == "\033[32m"


def test_refusal_status_is_two():
    """2 is "the control could not fire". 1 is "the tree has offenders"."""
    assert gate.EXIT_REFUSE == 2
    assert gate.EXIT_REFUSE != 1


def test_dirname_of_a_root_file_is_a_dot():
    """The one-character difference that made every root reference unmatchable.

    `dirname caller.yml` is `.` in the shell and `""` in Python, so the naive port produced `/victim.sh`, an absolute path matching nothing in any index. The gate would then have reported a clean tree for exactly the class of file the 2026-08-20 incident was about. Pinned here as well as in the selftest because it is a silent-blindness defect, and those are the ones worth two
    controls.
    """
    assert gate.resolve("caller.yml", "./victim.sh") == "victim.sh"
    assert gate.resolve("a/b.yml", "./victim.sh") == "a/victim.sh"


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    assert int(out.split(" control(s)")[0].strip()) >= 14


def test_the_twin_is_still_present():
    """Invariant 5: a twin is never deleted in the change that ports it."""
    assert (pathlib.Path(diff.repo()) / TWIN).is_file()
