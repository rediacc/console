"""`rediacc_ci.quality.python_lint`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-python-lint.sh` over a git fixture with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-python-lint.observations.jsonl`, which holds equivalence over six distinct trees. The twin has now been deleted and
every case that executed it compares against `goldens/python-lint/`, which holds the twin's OWN recorded output, captured from the tracked script on its last day in the tree. The provenance header of each golden carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed those bytes.

WHAT MADE THE FREEZE POSSIBLE, because it was blocked on exactly this for two sessions. `build()` used to `copytree` the LIVE `.ci/rediacc_ci/core/` into every specimen to clear `MIN_PY_FILES`, and the twin prints the corpus SIZE on every run, so a recording taken on any given day would have red the next time a peer added a module to one of the fastest-moving directories in the
tree. The padding is synthetic now (see `PAD_FILES`), the count is a fixed 12, and nothing outside this file decides it.

ONE DIFFERENCE BETWEEN THE RECORDED FIXTURE AND THIS ONE, named rather than left for a reader to notice. The recording ran the twin from INSIDE the specimen, because the twin derives its own root from `$BASH_SOURCE`, so the specimen carried a copy of the `.sh`. It cannot any more. That file is not Python, so it is invisible to every stage of the gate, and the claim was
driven rather than assumed before the deletion: the port over a specimen with the `.sh` removed and re-committed reproduces all eight recordings byte for byte.

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
import re
import shutil
import subprocess

import pytest

from rediacc_ci.quality import python_lint as gate
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

TWIN = ".ci/scripts/quality/check-python-lint.sh"
MODULE = "python_lint"
SLUG = "python-lint"

# The package files copied into every specimen. Enough of them to clear MIN_PY_FILES on their own, so a case that wants the floor to fire copies fewer rather than lowering the floor.
PACKAGE_FILES = ("__init__.py", "log.py", "paths.py", "controls.py", "proc.py", "gitx.py")

# PADDING, AND WHY IT IS SYNTHETIC RATHER THAN REAL.
#
# The specimen needs more than `MIN_PY_FILES` (10) files before the gate will rule on it at all, and the six `PACKAGE_FILES` plus the two quality-module files come to 8.
# This used to be made up by copytree-ing the LIVE `.ci/rediacc_ci/core/` in, which made every case here a hostage to that directory's current contents: `core/` is one of the fastest-growing directories in the repo, and a peer's half-written module landing there turns "a clean corpus passes" red for a reason that has nothing to do with this gate.
# Measured 2026-09-23: an in-flight `core/devbox.py` awaiting `ruff format` reds 3 of the 15 tests in this file.
#
# That coupling is fatal rather than merely annoying, because the twin is on its way out. The moment `check-python-lint.sh` is deleted, this differential's output gets frozen as a golden, and a golden that moves whenever a stranger adds a module cannot be re-recorded -- only hand-edited, which `.ci/rediacc_ci/tests/frozen.py:4-5` says defeats the point of freezing it.
#
# So the count is made up by files this file OWNS. One bare assignment each, which the repo's real `pyproject.toml` accepts as clean: `select = ["ALL"]` but with the `D` docstring rules and `INP001` ignored, which is the same reason the `probe_ok_lib.py` case below asserts exit 0 on `y = 2`.
PAD_FILES = 4


def _pad(root: pathlib.Path) -> None:
    """Fixed synthetic files, enough to carry the specimen over `MIN_PY_FILES`.

    8 real files + 4 here = 12 against a floor of 10, before any case's own `extra` files. Deliberately NOT called for the floor case, which needs to stay under.
    """
    for i in range(PAD_FILES):
        target = root / ".ci" / "rediacc_ci" / ("_pad%d.py" % i)
        target.write_text("pad%d = %d\n" % (i, i), encoding="utf-8")
        # Explicit, because the GIT mode is a subject of this gate: 100644 with no shebang is the combination EXE001 and EXE002 must both stay silent on.
        target.chmod(0o644)


def build(
    tmp_path: pathlib.Path,
    extra: dict[str, tuple[str, int]],
    *,
    with_padding: bool = True,
) -> pathlib.Path:
    """A sealed git specimen holding both implementations, the config, and `extra`.

    `extra` maps a path to (text, octal mode). The MODE is a subject of this gate (EXE001/EXE002 read the GIT mode), so it is explicit at every call site.

    `with_padding=False` leaves the specimen at 8 files, BELOW `MIN_PY_FILES`, which is how the floor case gets the gate to refuse. Every other case wants it True. See `PAD_FILES` for why the padding is synthetic.
    """
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    for rel in (".ci/rediacc_ci/quality", ".devcontainer"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    # `.ci/scripts/lib/` is still here because the port loads the toolchain pins through `toolchain.sh`, exactly as the twin did. The twin ITSELF is no longer copied in: it is deleted, and it was only ever in the specimen so its `$BASH_SOURCE`-derived root would land there.
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / "pyproject.toml", root / "pyproject.toml")
    shutil.copy2(src / ".devcontainer" / "toolchain.env", root / ".devcontainer" / "toolchain.env")
    # `.ci/cache/` holds the planted control file. Gitignored on purpose: "a crashed run cannot leave a stray .py that enumerate_py would pick up".
    (root / ".gitignore").write_text(".ci/cache/\n", encoding="utf-8")
    for name in PACKAGE_FILES:
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    if with_padding:
        _pad(root)
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


def run_port(root: pathlib.Path, prefix: str = "") -> tuple[int, str, str]:
    """The port over one specimen, with the fixture's own path masked out."""
    returncode, stdout, stderr = diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (prefix, MODULE),
        cwd=str(root),
    )
    return returncode, frozen.mask_root(stdout, root), frozen.mask_root(stderr, root)


def split_golden(text: str) -> tuple[int, str, str]:
    """A recorded twin render, back into its three parts."""
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def slug(case_id: str) -> str:
    """The golden's filename, DERIVED from the case id so the two cannot drift."""
    return re.sub(r"[^a-z0-9]+", "-", case_id.lower()).strip("-")


# The two cases that drove the twin from OUTSIDE the parametrized corpus. Named here rather than inline so `test_every_case_has_a_golden_and_no_golden_is_orphaned` can see the whole recorded set: a golden nothing reads and a case with no golden are both silent, and both are what that check exists for.
FLOOR_CASE = "the file floor refuses rather than reporting clean"
NO_RUFF_CASE = "a missing ruff is 77 and not 1"


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
    ("case_id", "extra", "want_exit"),
    CASES,
    ids=[c[0] for c in CASES],
)
def test_port_matches_the_twins_recorded_output(tmp_path, case_id, extra, want_exit):
    """Byte equality on BOTH streams against the twin's recording, plus the exit code."""
    root = build(tmp_path, extra)
    want_exit_recorded, want_out, want_err = split_golden(frozen.read(SLUG, slug(case_id)))
    returncode, stdout, stderr = run_port(root)
    assert want_exit_recorded == want_exit, "the recorded verdict moved"
    assert returncode == want_exit_recorded, "the twin exited %d, the port %d" % (
        want_exit_recorded,
        returncode,
    )
    assert stdout == want_out, "stdout diverged from the twin's recorded bytes"
    assert stderr == want_err, "stderr diverged from the twin's recorded bytes"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {slug(c[0]) for c in CASES} | {slug(FLOOR_CASE), slug(NO_RUFF_CASE)})


def test_a_clean_run_still_prints_ruffs_own_pass_line(tmp_path):
    """The byte a capturing port swallows, and only on the GREEN path.

    `$RUFF check --no-cache -- "${PY_FILES[@]}"` was a bare command in the twin, so
    ruff wrote straight to the gate's streams. A port that captured that output to inspect it drops `All checks passed!` when there is nothing to inspect -- a divergence a corpus built only from red specimens never sees. The recording is the twin's, so this still asserts the twin's byte and not the port's habit.
    """
    want_exit, want_out, _want_err = split_golden(frozen.read(SLUG, slug("a clean corpus passes")))
    assert want_exit == 0
    assert "All checks passed!" in want_out, "the green recording lost ruff's own pass line"
    returncode, stdout, _stderr = run_port(build(tmp_path, {}))
    assert returncode == 0
    assert stdout == want_out


def test_the_file_floor_refuses_rather_than_reporting_clean(tmp_path):
    """`ruff check` with no paths exits 0, so a shrinking input reads as clean.

    NOT IN THE LEDGER: the refusal says `VACUOUS INPUT`, and `scripts/lib/shadow-gate.ts` treats that vocabulary as a suspended comparison rather than a verdict. Byte equality can rule on it, so it lived here while the twin did and its recording lives here now.
    """
    want_exit, want_out, want_err = split_golden(frozen.read(SLUG, slug(FLOOR_CASE)))
    returncode, stdout, stderr = run_port(build(tmp_path, {}, with_padding=False))
    assert want_exit == 1
    assert returncode == want_exit
    assert stdout == want_out
    assert stderr == want_err
    assert "VACUOUS INPUT" in want_err
    assert "expected at least %d" % gate.MIN_PY_FILES in want_err


def test_a_missing_ruff_is_77_and_not_1(tmp_path):
    """77 is CANNOT RUN. 1 would say "ruff found a problem", which is false.

    Driven by handing the gate a PATH with neither ruff nor uvx on it, which is an ENVIRONMENT difference rather than a tree difference and therefore cannot be a ledger row.
    """
    want_exit, want_out, want_err = split_golden(frozen.read(SLUG, slug(NO_RUFF_CASE)))
    returncode, stdout, stderr = run_port(build(tmp_path, {}), prefix="PATH=/usr/bin:/bin")
    assert want_exit == gate.EXIT_CANNOT_RUN, want_err
    assert returncode == want_exit, stderr
    assert stdout == want_out
    assert stderr == want_err
    assert "NOT skipping" in want_err
    # THE STANDALONE INSTALLER IS FIRST because it is the one that works in the devbox, where `python3 -m pip` reports "No module named pip".
    lines = [line for line in want_err.split("\n") if "install one of" in line or "://" in line]
    assert any("astral.sh/ruff" in line for line in lines), want_err


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
    reads. The two agree today; this asserts that, so the day they diverge the divergence is a red test rather than a gate silently demanding an old version.
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


def test_the_twin_is_gone_and_its_recording_names_it() -> None:
    """The retirement, asserted rather than assumed.

    A golden whose provenance header had been hand-written, or copied from a sibling, would look identical to a recorded one and would be evidence of nothing. So the header is required to name THIS twin, and the twin is required to be absent: a tree holding both would mean the recording was never the reason the comparison stopped executing bash.
    """
    assert not (pathlib.Path(diff.repo()) / TWIN).exists(), (
        "the twin is back; compare against it rather than its recording"
    )
    for case_id in [c[0] for c in CASES] + [FLOOR_CASE, NO_RUFF_CASE]:
        path = frozen.directory(SLUG) / ("%s.golden" % slug(case_id))
        header = path.read_text(encoding="utf-8").split("\n", 1)[0]
        assert header.startswith("# twin %s blob " % TWIN), header


def test_the_recorded_green_is_not_vacuously_equal() -> None:
    """Two implementations that both print nothing agree about nothing.

    Three of the eight recordings exit 0, and a port could match any of them by printing nothing at all if the recording were empty. The green path must still SAY what it measured, on STDOUT, and leave STDERR clean; the refusals are the other way round. The split is the twin's, and `scripts/lib/shadow-gate.ts` reads the two streams differently, so a recording that had
    collapsed both onto one stream would weaken every comparison above without failing any of them.
    """
    green = split_golden(frozen.read(SLUG, slug("a clean corpus passes")))
    refusal = split_golden(frozen.read(SLUG, slug(NO_RUFF_CASE)))
    assert green[0] == 0
    assert refusal[0] == gate.EXIT_CANNOT_RUN
    assert "%d Python file(s) pass" % (len(PACKAGE_FILES) + PAD_FILES + 2) in green[1]
    assert green[2] == "", "the green case leaked a finding onto stderr"
    assert refusal[1] == "", "the refusal leaked onto stdout"
    assert refusal[2].strip() != ""


def test_a_planted_defect_is_caught_by_the_goldens(tmp_path) -> None:
    """THE CONTROL ON THE GOLDENS: the clean corpus, mutated into a red one.

    Comparing two recordings against each other would prove only that two files differ. This runs the port over a specimen carrying a real ruff violation and requires it to diverge from the GREEN recording, so a goldens comparison that had quietly stopped executing the port cannot report a pass.
    """
    green = split_golden(frozen.read(SLUG, slug("a clean corpus passes")))
    root = build(tmp_path, {"probe_planted.py": ("def f():\n    return not_a_name\n", 0o644)})
    returncode, stdout, stderr = run_port(root)
    assert returncode == 1, "the planted F821 passed, so the goldens above prove nothing"
    assert stdout != green[1], "the mutant printed the green recording's stdout"
    assert stderr.strip() != "", "the mutant reported no finding"
