"""Differential: `rediacc_ci.diagnostics.collect_drill_diagnostics` against its
twin `.ci/scripts/test/collect-drill-diagnostics.sh`.

Both subjects derive the console root from their own file location
(three directories up), so both COPIES live in one shared fixture tree at the
right relative depth; the tool is read-only with respect to that tree (it only
ever creates a fresh `$RUNNER_TEMP/drill-diagnostics`), so unlike a mutating
teardown script the two sides can safely share one source fixture and differ
only in `RUNNER_TEMP`/`TMPDIR`, which route each side's collection to its own
scratch directory.

K=5 LEDGER: `.ci/shadow/w7p6-collect-drill-diagnostics.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "test" / "collect-drill-diagnostics.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "diagnostics" / "collect_drill_diagnostics.py"


def _fixture(tmp_path: pathlib.Path, *, account_logs: bool, drills: list[str]) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects."""
    root = tmp_path / "tree"
    (root / ".ci" / "scripts" / "test").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "diagnostics").mkdir(parents=True)
    shutil_copy(TWIN, root / ".ci" / "scripts" / "test" / TWIN.name)
    shutil_copy(PORT, root / ".ci" / "rediacc_ci" / "diagnostics" / PORT.name)
    if account_logs:
        acct = root / ".account-logs"
        acct.mkdir()
        (acct / "rustfs.log").write_text("rustfs booted\n", encoding="utf-8")
    for name in drills:
        work = tmp_path / "tmproot" / name
        work.mkdir(parents=True)
        (work / "gateway.log").write_text(f"gateway log for {name}\n", encoding="utf-8")
    return root


def shutil_copy(src: pathlib.Path, dst: pathlib.Path) -> None:
    shutil.copy2(src, dst)
    dst.chmod(0o755)


def _run(
    subject: pathlib.Path, root: pathlib.Path, tmp_path: pathlib.Path
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    runner_temp = tmp_path / ("out-%s" % subject.suffix.lstrip("."))
    runner_temp.mkdir(exist_ok=True)
    tmproot = tmp_path / "tmproot"
    tmproot.mkdir(exist_ok=True)
    env["RUNNER_TEMP"] = str(runner_temp)
    env["TMPDIR"] = str(tmproot)
    if subject.suffix == ".sh":
        subject_dir = root / ".ci" / "scripts" / "test"
        cmd = ["bash", str(subject_dir / subject.name)]
    else:
        subject_dir = root / ".ci" / "rediacc_ci" / "diagnostics"
        cmd = ["python3", str(subject_dir / subject.name)]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, check=False, timeout=30)


def _both(tmp_path: pathlib.Path, *, account_logs: bool, drills: list[str]):
    """Run both subjects and NORMALIZE the one legitimate difference: each side
    is deliberately given its own `$RUNNER_TEMP` (a mutating collector cannot
    safely share a destination between two runs), and that path is printed
    verbatim in `$dest`. Comparing stdout with each side's own scratch prefix
    stripped is the same idea `differential.py`'s `<repo>` substitution uses for
    the checkout root."""
    root = _fixture(tmp_path, account_logs=account_logs, drills=drills)
    old = _run(TWIN, root, tmp_path)
    new = _run(PORT, root, tmp_path)
    old_norm = old.stdout.replace(str(tmp_path / "out-sh"), "<out>")
    new_norm = new.stdout.replace(str(tmp_path / "out-py"), "<out>")
    return old, new, old_norm, new_norm


def test_nothing_to_collect_is_reported_not_fatal(tmp_path: pathlib.Path) -> None:
    old, new, old_norm, new_norm = _both(tmp_path, account_logs=False, drills=[])
    assert old.returncode == 0
    assert new.returncode == 0
    assert "collected: 0 file(s)" in old.stdout
    assert "nothing collected" in old.stdout
    assert new_norm == old_norm


def test_account_logs_alone(tmp_path: pathlib.Path) -> None:
    old, _new, old_norm, new_norm = _both(tmp_path, account_logs=True, drills=[])
    assert "collected: 1 file(s)" in old.stdout
    assert new_norm == old_norm


def test_one_drill_dir_alone(tmp_path: pathlib.Path) -> None:
    old, _new, old_norm, new_norm = _both(
        tmp_path, account_logs=False, drills=["rediacc-drill-abc123"]
    )
    assert "collected: 1 file(s)" in old.stdout
    assert "rediacc-drill-abc123" in old.stdout
    assert new_norm == old_norm


def test_multiple_drill_dirs_are_glob_sorted(tmp_path: pathlib.Path) -> None:
    """The twin's glob sorts lexicographically; `sorted()` in the port must
    match it rather than an incidental filesystem order."""
    old, _new, old_norm, new_norm = _both(
        tmp_path, account_logs=True, drills=["rediacc-drill-zzz", "rediacc-drill-aaa"]
    )
    assert "collected: 3 file(s)" in old.stdout
    assert new_norm == old_norm


def test_the_fake_is_actually_reached(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Without a real collected file, every comparison above is
    two empty collections agreeing trivially."""
    old, _new, old_norm, new_norm = _both(tmp_path, account_logs=True, drills=["rediacc-drill-x"])
    assert "collected: 2 file(s)" in old.stdout, "the fixture never produced a real file: %r" % (
        old.stdout,
    )
    assert "bytes" in old.stdout
    assert new_norm == old_norm
