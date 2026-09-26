"""`rediacc_ci.diagnostics.collect_drill_diagnostics`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/test/collect-drill-diagnostics.sh` and the port over one shared fixture tree and compared stdout with each side's own `$RUNNER_TEMP` masked out. The K=5 ledger `.ci/shadow/w7p6-collect-drill-diagnostics.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted, and every case
compares against `goldens/collect-drill-diagnostics/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. The provenance header carries the twin's blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

BOTH SUBJECTS DERIVE THE CONSOLE ROOT FROM THEIR OWN FILE LOCATION, three directories up, so the fixture tree still holds a COPY of the port at that relative depth rather than running the tracked file in place. The tool is read-only with respect to that tree: it only ever creates a fresh `$RUNNER_TEMP/drill-diagnostics`.

WHAT IS NORMALISED, and it is two things rather than one.

  * `$RUNNER_TEMP` is printed verbatim in the destination path and in every listing line, and a recording is compared against a tree built under a different tempdir name months later. It becomes `<out>`, which is the substitution the differential already made for the same reason.
  * THE ORDER OF THE LISTING LINES, which is the one thing a recording cannot inherit from the differential. The twin's final listing was `find "$dest" -type f`, which imposes no order of its own, and the port's `os.walk` imposes none either; while both ran they were two readers of ONE kernel directory in the same second and got the same enumeration back, so the order agreed
    without ever being an assertion. A golden is compared against a directory built later, possibly on a different filesystem, whose readdir order is that filesystem's business. So the listing lines are compared as a SORTED MULTISET, and the count line -- which is `find | wc -l`, an order-free number -- is compared in place, verbatim. Nothing else is touched: the byte content
    of every line, the two-space indent, the ten-column size field and the `(nothing collected ...)` floor are all compared exactly as recorded.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "diagnostics" / "collect_drill_diagnostics.py"
SLUG = "collect-drill-diagnostics"

# name -> the fixture this case is collected from
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "nothing-to-collect": {"account_logs": False, "drills": []},
    "account-logs-alone": {"account_logs": True, "drills": []},
    "one-drill-dir-alone": {"account_logs": False, "drills": ["rediacc-drill-abc123"]},
    "many-drill-dirs-glob-sorted": {
        "account_logs": True,
        "drills": ["rediacc-drill-zzz", "rediacc-drill-aaa"],
    },
    "account-logs-and-one-drill": {"account_logs": True, "drills": ["rediacc-drill-x"]},
}

CASES = tuple(CASE_KW)

LISTING_PREFIX = "  "
COUNT_PREFIX = "drill diagnostics collected: "


def fixture(tmp_path: pathlib.Path, *, account_logs: bool, drills: list[str]) -> pathlib.Path:
    """A tree shaped like the repository, holding a COPY of the port at its own depth."""
    root = tmp_path / "tree"
    (root / ".ci" / "rediacc_ci" / "diagnostics").mkdir(parents=True, exist_ok=True)
    copy_subject(PORT, root / ".ci" / "rediacc_ci" / "diagnostics" / PORT.name)
    if account_logs:
        acct = root / ".account-logs"
        acct.mkdir(exist_ok=True)
        (acct / "rustfs.log").write_text("rustfs booted\n", encoding="utf-8")
    for name in drills:
        work = tmp_path / "tmproot" / name
        work.mkdir(parents=True, exist_ok=True)
        (work / "gateway.log").write_text("gateway log for %s\n" % name, encoding="utf-8")
    return root


def copy_subject(src: pathlib.Path, dst: pathlib.Path) -> None:
    shutil.copy2(src, dst)
    dst.chmod(0o755)


def run(tmp_path: pathlib.Path, name: str, *, subject: str = PORT.name) -> tuple[int, str, str]:
    """One run of the port over this case's own fixture, with `$RUNNER_TEMP` masked."""
    root = fixture(tmp_path, **CASE_KW[name])
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    tmproot = tmp_path / "tmproot"
    tmproot.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["RUNNER_TEMP"] = str(out)
    env["TMPDIR"] = str(tmproot)
    proc = subprocess.run(
        ["python3", str(root / ".ci" / "rediacc_ci" / "diagnostics" / subject)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    return (
        proc.returncode,
        proc.stdout.replace(str(out), "<out>"),
        proc.stderr.replace(str(out), "<out>"),
    )


def recorded(name: str) -> tuple[int, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def order_free(stdout: str) -> tuple[str, tuple[str, ...]]:
    """The count line and the floor in place, the listing lines as a sorted multiset.

    Splitting on the indent rather than on line position is deliberate: a port that dropped the count line and printed one more listing line changes the first element of the tuple rather than quietly reshuffling the second.
    """
    lines = stdout.split("\n")
    listing = tuple(sorted(x for x in lines if x.startswith(LISTING_PREFIX) and "bytes" in x))
    spine = "\n".join(x for x in lines if not (x.startswith(LISTING_PREFIX) and "bytes" in x))
    return spine, listing


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str]:
    want = recorded(name)
    got = run(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert order_free(got[1]) == order_free(want[1]), "%s: stdout diverged: %r vs %r" % (
        name,
        want[1],
        got[1],
    )
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_nothing_to_collect_is_reported_not_fatal() -> None:
    """The floor is the message: an empty collection exits 0 and says so."""
    code, stdout, _ = recorded("nothing-to-collect")
    assert code == 0
    assert stdout.startswith("%s0 file(s) under <out>/drill-diagnostics\n" % COUNT_PREFIX)
    assert "(nothing collected -- check that the drills ran with --keep-work)" in stdout


def test_the_fixture_is_actually_reached() -> None:
    """ANTI-VACUITY on the fixtures. Without a real collected file every comparison above is two empty collections agreeing trivially, so the recordings are asserted to carry real bytes."""
    _, stdout, _ = recorded("account-logs-and-one-drill")
    assert "%s2 file(s)" % COUNT_PREFIX in stdout
    assert "14 bytes  <out>/drill-diagnostics/account-logs/rustfs.log" in stdout
    assert "32 bytes  <out>/drill-diagnostics/rediacc-drill-x/gateway.log" in stdout


def test_both_sources_and_the_glob_are_recorded() -> None:
    """The two collection arms and the multi-drill case, read off the recordings."""
    assert "%s1 file(s)" % COUNT_PREFIX in recorded("account-logs-alone")[1]
    assert "rediacc-drill-abc123/gateway.log" in recorded("one-drill-dir-alone")[1]
    _, many, _ = recorded("many-drill-dirs-glob-sorted")
    assert "%s3 file(s)" % COUNT_PREFIX in many
    assert "rediacc-drill-aaa/gateway.log" in many
    assert "rediacc-drill-zzz/gateway.log" in many


def test_nothing_is_written_to_stderr() -> None:
    """Every `cp` and `find` in the twin was `2>/dev/null || true`, so a port letting an error through is visible here."""
    for name in CASES:
        assert recorded(name)[2] == "", "%s recorded stderr" % name


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_drop_of_the_account_logs_arm_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Make the `.account-logs` arm unreachable.

    That arm is the half of the collection no drill work directory can supply, and the failure it exists to catch (`docker compose up -d config-rustfs` dying invisibly) is readable nowhere else. `account-logs-and-one-drill` records two files; a mutant that skips the copy collects one and names a different count. The mutation runs from a throwaway copy of the module inside the
    fixture tree, at the depth `_root()` needs; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "    if account_logs.is_dir():\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "    if not account_logs.is_dir():\n")

    name = "account-logs-and-one-drill"
    root = fixture(tmp_path / "planted", **CASE_KW[name])
    mutant = root / ".ci" / "rediacc_ci" / "diagnostics" / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")
    _, stdout, _ = run(tmp_path / "planted", name, subject="mutant.py")

    want = recorded(name)[1]
    assert "%s2 file(s)" % COUNT_PREFIX in want, "the recorded corpus moved"
    assert "%s1 file(s)" % COUNT_PREFIX in stdout, "the plant did not change the collection"
    assert "account-logs/rustfs.log" not in stdout

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
