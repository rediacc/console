"""`rediacc_ci.quality.python_lint` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-python-lint.sh` over a git fixture with stdout and stderr captured SEPARATELY, and its bytes are compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-python-lint.observations.jsonl`.

THE FIXTURE CARRIES THE REAL `pyproject.toml`, and it has to. The control this gate runs before judging anything asserts that F821 and ARG001 are reported and that ANN001 is NOT, which pins three separate facts about the configuration that ruff DISCOVERED by walking up from the file it linted. A fixture without that file would be linted with ruff's defaults, would still report
F821, and would prove nothing -- which is the exact trap the twin's comment describes.

TWO THINGS THIS FILE PROVES THAT THE LEDGER CANNOT.

  * THE FILE FLOOR fires with a `VACUOUS INPUT` message, and
    `scripts/lib/shadow-gate.ts` classifies that vocabulary as a REFUSAL, which
    SUSPENDS the comparison rather than ruling on it. So the floor case is
    unrecordable by construction and lives here.
  * EXIT 77 requires a PATH with neither ruff nor uvx on it. That is an
    environment difference rather than a tree difference, and the ledger keys on
    tree content, so it lives here too. 77 is CANNOT RUN and must never be
    confused with 1: exit 1 would say "ruff found a problem", which is false, and
    which once made a pre-push lane refuse every push on a machine that simply
    lacked the tool.

A NOTE ON PLANTING DEFECTS IN THIS PARTICULAR PORT, because it cost a wasted control. This gate LINTS ITS OWN PORT FILE: `.ci/rediacc_ci/quality/python_lint.py` is inside the enumerated corpus. A planted defect that is itself a ruff violation (`if False and ...` trips SIM223) is caught by the ruff-check stage on BOTH sides and the run never reaches the planted branch, so the
comparator scores EQUIVALENT and the plant looks like a gate that cannot fail. It is not: the plant was at fault. Plant something ruff accepts -- changing a compared literal, for instance.
"""

import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci.quality import python_lint as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-python-lint.sh"
MODULE = "python_lint"

# The package files copied into every specimen. Enough of them to clear MIN_PY_FILES on their own, so a case that wants the floor to fire copies fewer rather than lowering the floor.
PACKAGE_FILES = ("__init__.py", "log.py", "paths.py", "controls.py", "proc.py", "gitx.py")


def build(
    tmp_path: pathlib.Path,
    extra: dict[str, tuple[str, int]],
    *,
    with_core: bool = True,
) -> pathlib.Path:
    """A sealed git specimen holding both implementations, the config, and `extra`.

    `extra` maps a path to (text, octal mode). The MODE is a subject of this gate (EXE001/EXE002 read the GIT mode), so it is explicit at every call site.
    """
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    for rel in (".ci/scripts/quality", ".ci/rediacc_ci/quality", ".devcontainer"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    shutil.copy2(src / "pyproject.toml", root / "pyproject.toml")
    shutil.copy2(src / ".devcontainer" / "toolchain.env", root / ".devcontainer" / "toolchain.env")
    # `.ci/cache/` holds the planted control file. Gitignored on purpose: "a crashed run cannot leave a stray .py that enumerate_py would pick up".
    (root / ".gitignore").write_text(".ci/cache/\n", encoding="utf-8")
    for name in PACKAGE_FILES:
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    if with_core:
        shutil.copytree(src / ".ci" / "rediacc_ci" / "core", root / ".ci" / "rediacc_ci" / "core")
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    for rel, (text, mode) in extra.items():
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


def run_both(
    root: pathlib.Path, prefix: str = ""
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old = diff.bash_streams("%s bash %s" % (prefix, TWIN), cwd=str(root))
    new = diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (prefix, MODULE),
        cwd=str(root),
    )
    return old, new


CASES = [
    # THE NEGATIVE HALF. A clean corpus must exit 0 AND print ruff's own "All checks passed!" line, which is the byte the port lost when it captured ruff's output in order to inspect it.
    ("a clean corpus passes", {}, 0),
    (
        "an undefined name is reported",
        {"probe_bad.py": ("def planted():\n    return undefined_on_purpose\n", 0o644)},
        1,
    ),
    (
        "a formatting difference names the file that differs",
        {"probe_fmt.py": ("x = [1,2,3]\ndef f( a ):\n    return a\n", 0o644)},
        1,
    ),
    (
        # EXE001. The property is the GIT mode, not the disk mode: CI lints a fresh checkout, so what it sees is whatever git recorded.
        "a shebang with git mode 100644 is EXE001",
        {"probe_exe.py": ("#!/usr/bin/env python3\nx = 1\n", 0o644)},
        1,
    ),
    (
        # EXE002, the other direction. Both are defects.
        "no shebang with git mode 100755 is EXE002",
        {"probe_noshebang.py": ("x = 1\n", 0o755)},
        1,
    ),
    (
        # AND THE NEGATIVE HALF OF BOTH: the agreeing combinations must be silent, or the mode scan is a blanket refusal.
        "a shebang with git mode 100755 is fine, and no shebang with 100644 is too",
        {
            "probe_ok_exe.py": ("#!/usr/bin/env python3\nx = 1\n", 0o755),
            "probe_ok_lib.py": ("y = 2\n", 0o644),
        },
        0,
    ),
]


@pytest.mark.parametrize(
    ("extra", "want_exit"),
    [(c[1], c[2]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_differential(tmp_path, extra, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, extra)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == want_exit, "the twin's verdict moved: %s%s" % (old_out, old_err)
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


def test_a_clean_run_still_prints_ruffs_own_pass_line(tmp_path):
    """The byte a capturing port swallows, and only on the GREEN path.

    `$RUFF check --no-cache -- "${PY_FILES[@]}"` is a bare command in the twin, so
    ruff writes straight to the gate's streams. A port that captured that output to inspect it drops `All checks passed!` when there is nothing to inspect -- a divergence a differential built only from red specimens never sees.
    """
    root = build(tmp_path, {})
    (old_rc, old_out, _old_err), (new_rc, new_out, _new_err) = run_both(root)
    assert old_rc == 0
    assert new_rc == 0
    assert "All checks passed!" in old_out
    assert new_out == old_out


def test_the_file_floor_refuses_rather_than_reporting_clean(tmp_path):
    """`ruff check` with no paths exits 0, so a shrinking input reads as clean.

    NOT IN THE LEDGER: the refusal says `VACUOUS INPUT`, and `scripts/lib/shadow-gate.ts` treats that vocabulary as a suspended comparison rather than a verdict. Byte equality can rule on it, so it lives here.
    """
    root = build(tmp_path, {}, with_core=False)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == 1
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err
    assert "VACUOUS INPUT" in old_err
    assert "expected at least %d" % gate.MIN_PY_FILES in old_err


def test_a_missing_ruff_is_77_and_not_1(tmp_path):
    """77 is CANNOT RUN. 1 would say "ruff found a problem", which is false.

    Driven by handing the gate a PATH with neither ruff nor uvx on it, which is an ENVIRONMENT difference rather than a tree difference and therefore cannot be a ledger row.
    """
    root = build(tmp_path, {})
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(
        root, prefix="PATH=/usr/bin:/bin"
    )
    assert old_rc == gate.EXIT_CANNOT_RUN, old_err
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err
    assert "NOT skipping" in old_err
    # THE STANDALONE INSTALLER IS FIRST because it is the one that works in the devbox, where `python3 -m pip` reports "No module named pip".
    lines = [line for line in old_err.split("\n") if "install one of" in line or "://" in line]
    assert any("astral.sh/ruff" in line for line in lines), old_err


def test_the_control_verdict_pins_three_separate_facts():
    """F821 present, ARG001 present, ANN001 ABSENT. Any one alone is satisfiable.

    Measured 2026-09-06: `--isolated` reports F821 only, `--isolated --select ALL` reports F821 + ARG001 + ANN001 + more, and this repo's config reports F821 + ARG001. So the three-way test is what tells a resolved config from no config at all.
    """
    assert gate.control_verdict("F821\nARG001\n") == ""
    assert "F821 was not reported" in gate.control_verdict("ARG001\n")
    assert 'select = ["ALL"]' in gate.control_verdict("F821\n")
    assert "ignore list" in gate.control_verdict("F821\nARG001\nANN001\n")


def test_the_unformatted_parser_survives_ruffs_colour():
    """ruff colours through a pipe, and an anchored match without a strip finds nothing.

    That silent failure fell back to naming all 80 tracked files, which is the very thing the parser exists to stop.
    """
    assert gate.unformatted_paths("\x1b[1m\x1b[94m--> \x1b[0ma/b.py:1:1\n") == "a/b.py "
    assert gate.unformatted_paths("  --> z.py:1\n  --> a.py:1\n") == "a.py z.py "
    assert gate.unformatted_paths("All checks passed!\n") == ""


def test_colour_is_decided_by_ci_not_by_a_terminal(monkeypatch):
    """One of the nine disagreeing conventions, reproduced rather than corrected.

    Using `rediacc_ci.log` here would decide colour by `isatty` and change the bytes on every non-CI run, so every differential above would mismatch.
    """
    monkeypatch.setenv("CI", "true")
    assert gate.colours() == ("", "", "")
    monkeypatch.setenv("CI", "false")
    assert gate.colours() == ("\033[0;31m", "\033[0;32m", "\033[0m")
    monkeypatch.delenv("CI", raising=False)
    assert gate.colours() == ("\033[0;31m", "\033[0;32m", "\033[0m")


def test_the_pin_the_twin_compares_against_matches_the_pins_file():
    """The twin assigns RUFF_VERSION twice and the literal wins.

    `toolchain_load` exports the pins-file value and the next line overwrites it
    with `RUFF_VERSION="0.16.1"`, which is what `toolchain_pin_for ruff` then
    reads. The two agree today; this asserts that, so the day they diverge the
    divergence is a red test rather than a gate silently demanding an old version.
    """
    pins = (pathlib.Path(diff.repo()) / ".devcontainer" / "toolchain.env").read_text(
        encoding="utf-8"
    )
    declared = [
        line.split("=", 1)[1].strip()
        for line in pins.split("\n")
        if line.startswith("RUFF_VERSION=")
    ]
    assert declared == [gate.RUFF_VERSION], (
        "the twin hardcodes %r while .devcontainer/toolchain.env says %r"
        % (gate.RUFF_VERSION, declared)
    )


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
