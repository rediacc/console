"""The controls for `rediacc_ci.core.tmp_capacity` and its two wirings (worklist #edd646a8).

Three layers, each with a case that must fire and one that must not:
  - the pure check, fed fake statvfs readings through its `reader` seam: below each floor it refuses with the path, the used/total inodes, the percentage and the fix; above it passes;
  - the repo-root conftest.py, through a REAL nested pytest run: the floor raised over the live filesystem's free inodes aborts it before collection with the one line, and the same run without the plant collects normally;
  - scripts/ci-runner/run.ts, through a REAL runner process: the same plant exits 1 with the same line before any gate is selected.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci.core import tmp_capacity as T

ROOT = pathlib.Path(__file__).resolve().parents[3]
GIB = 1 << 30
# Far above any real filesystem's free inodes, so the live reading is below it on every machine.
PLANT = str(10**15)


def reading(total=1_048_576, free=500_000, free_bytes=10 * GIB, path="/fake/tmp") -> T.Reading:
    return T.Reading(
        path=path,
        total_inodes=total,
        free_inodes=free,
        total_bytes=30 * GIB,
        free_bytes=free_bytes,
    )


def run_check(fake: T.Reading, floor: T.Floor | None = None) -> tuple[bool, str]:
    return T.check(
        ["/fake/tmp"],
        floor=floor or T.Floor(),
        reader=lambda _p: fake,
        walker=lambda p: "biggest: %s/scratchpad 900,000" % p,
    )


def test_the_incident_reading_is_refused_with_one_named_line():
    """1,330 free of 1,048,576: the hook run that reported 921 errors and named nothing about inodes."""
    ok, line = run_check(reading(free=1_330))
    assert not ok
    assert "\n" not in line, "the refusal must be ONE line: %r" % line
    for needle in (
        "REFUSING to start",
        "/fake/tmp",
        "1,047,246 of 1,048,576 inodes used (99.9%)",
        "1,330 free",
        "1,330 inodes free < 100,000",
        "biggest: /fake/tmp/scratchpad 900,000",
        "--prune-scratch",
    ):
        assert needle in line, "missing %r in %s" % (needle, line)


def test_the_ci_quick_reading_is_refused_too():
    """93% used, about 73,000 free: the run that broke `ci:quick`. A floor below this would have passed the very run it exists for."""
    ok, line = run_check(reading(free=73_000))
    assert not ok, line
    assert "73,000 inodes free < 100,000" in line, line


def test_a_healthy_reading_passes_and_prints_its_shape():
    ok, line = run_check(reading(free=500_000))
    assert ok, line
    assert line.startswith("tmp-capacity: ok, /fake/tmp: 548,576 of 1,048,576 inodes used"), line
    assert "floor 100,000 inodes" in line


def test_the_boundary_is_exact():
    assert run_check(reading(free=T.MIN_FREE_INODES))[0]
    assert not run_check(reading(free=T.MIN_FREE_INODES - 1))[0]


def test_the_percentage_floor_binds_on_a_large_filesystem():
    """30M inodes with 1M free clears the absolute floor and is still 96.7% used."""
    ok, line = run_check(reading(total=30_000_000, free=1_000_000))
    assert not ok, line
    assert "3.3% inodes free < 5%" in line, line
    assert run_check(reading(total=30_000_000, free=2_000_000))[0]


def test_the_space_floor():
    ok, line = run_check(reading(free_bytes=GIB // 2))
    assert not ok, line
    assert "0.5 GiB free < 1.0 GiB" in line, line
    assert run_check(reading(free_bytes=GIB))[0]


def test_a_filesystem_without_an_inode_ceiling_is_not_read_as_zero_free():
    """btrfs reports f_files == 0. That is no ceiling, not a full filesystem."""
    ok, line = run_check(reading(total=0, free=0))
    assert ok, line
    assert "no inode ceiling" in line, line


def test_an_unreadable_filesystem_is_unchecked_and_refused():
    def broken(_p):
        raise OSError(5, "Input/output error")

    ok, line = T.check(["/fake/tmp"], floor=T.Floor(), reader=broken, walker=lambda _p: "")
    assert not ok, line
    assert "UNCHECKED" in line, line
    assert "Input/output error" in line, line


def test_the_override_only_raises_the_floor():
    assert T.floor_from_env({}).min_free_inodes == T.MIN_FREE_INODES
    assert T.floor_from_env({T.FLOOR_ENV: "250000"}).min_free_inodes == 250_000
    # Lowering it would be a switch for getting past the check, so a lower value is ignored.
    assert T.floor_from_env({T.FLOOR_ENV: "0"}).min_free_inodes == T.MIN_FREE_INODES
    for bad in ("abc", "-5", "1e6"):
        with pytest.raises(ValueError, match=T.FLOOR_ENV):
            T.floor_from_env({T.FLOOR_ENV: bad})


def test_a_malformed_override_is_a_refusal_not_a_fallback(monkeypatch):
    monkeypatch.setenv(T.FLOOR_ENV, "lots")
    ok, line = T.check(["/fake/tmp"], reader=lambda _p: reading(), walker=lambda _p: "")
    assert not ok, line
    assert "is not an integer" in line, line


def test_the_live_filesystem_is_read():
    """The real statvfs, so the seam above is not the only thing ever exercised."""
    got = T.read(str(ROOT))
    assert got.total_bytes > 0
    assert got.free_bytes > 0
    # A path that does not exist yet (a basetemp before pytest creates it) is read on its nearest existing ancestor.
    assert T.read(str(ROOT / "no" / "such" / "dir")).path == str(ROOT)


def test_consumers_names_where_the_inodes_concentrate(tmp_path):
    """The biggest child of the root is drilled down through dominant children, the way /tmp/claude-1000 resolves to the session scratchpad that holds the clones."""
    pad = tmp_path / "claude-1" / "proj" / "sess" / "scratchpad"
    # No clone holds half the scratchpad, so the drill stops AT the scratchpad and lists them; one that did would itself be the answer.
    for name, n in (("aclone", 20), ("bclone", 15), ("cclone", 10)):
        d = pad / name
        d.mkdir(parents=True)
        for i in range(n):
            (d / ("f%d" % i)).write_text("x")
    other = tmp_path / "pytest-of-x"
    other.mkdir()
    for i in range(5):
        (other / ("g%d" % i)).write_text("x")
    # A symlink to a big tree is ONE inode here, never a walk into the target.
    (tmp_path / "link").symlink_to(pad)
    said = T.consumers(str(tmp_path))
    assert said.startswith("biggest: %s 49" % pad), said
    assert "[aclone 21, bclone 16, cclone 11]" in said, said
    assert "%s 6" % other in said, said
    assert "partial" not in said


def test_consumers_says_when_its_walk_was_capped(tmp_path):
    for i in range(5):
        (tmp_path / ("d%d" % i)).mkdir()
    ticks = iter(range(1000))
    said = T.consumers(str(tmp_path), budget_s=2, clock=lambda: float(next(ticks)))
    assert "partial, walk capped at 2s" in said, said


def _nested_pytest(
    cache: pathlib.Path, extra_env: dict[str, str], *args: str
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop(T.FLOOR_ENV, None)
    env.update(extra_env)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            # Its own cache, not `-p no:cacheprovider`: that makes pyproject's `cache_dir` an unknown ini key, which is rc=4 for a reason that has nothing to do with this check (the first cut's control caught exactly that).
            "-o",
            "cache_dir=%s" % cache,
            "--collect-only",
            "-q",
            *args,
            "%s::test_the_boundary_is_exact" % pathlib.Path(__file__).relative_to(ROOT),
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_the_conftest_aborts_a_real_pytest_run_with_the_one_line(tmp_path):
    """THE WIRING CONTROL. The plant raises the floor over the live filesystem; the control is the identical command without it."""
    planted = _nested_pytest(tmp_path, {T.FLOOR_ENV: PLANT})
    assert planted.returncode == 4, (
        planted.returncode,
        planted.stdout[-400:],
        planted.stderr[-400:],
    )
    assert "tmp-capacity: REFUSING to start" in planted.stderr, planted.stderr[-600:]
    assert "test_the_boundary_is_exact" not in planted.stdout, "collection ran past the refusal"

    control = _nested_pytest(tmp_path, {})
    assert control.returncode == 0, (
        control.returncode,
        control.stdout[-400:],
        control.stderr[-400:],
    )
    assert "test_the_boundary_is_exact" in control.stdout


def test_the_conftest_refuses_in_the_xdist_controller_before_any_worker(tmp_path):
    planted = _nested_pytest(tmp_path, {T.FLOOR_ENV: PLANT}, "-n", "2")
    assert planted.returncode == 4, (planted.returncode, planted.stderr[-400:])
    assert "tmp-capacity: REFUSING to start" in planted.stderr
    assert "INTERNALERROR" not in planted.stdout + planted.stderr


def test_the_ci_runner_refuses_before_selecting_a_gate():
    """THE OTHER WIRING CONTROL, through a real runner process. A missing tsx FAILS rather than returning: a test that returns early counts as a pass, and the wiring control would never have run (review ea950842.3). Every lane that runs this suite installs node_modules (setup-workspace in quality-pytest)."""
    assert (ROOT / "node_modules" / "tsx").exists(), (
        "node_modules/tsx is missing, so the ci-runner wiring control cannot run: npm ci, then rerun"
    )
    env = dict(os.environ)
    env[T.FLOOR_ENV] = PLANT
    got = subprocess.run(
        ["npx", "--no-install", "tsx", "scripts/ci-runner/run.ts", "--only", "check:ci-npmrc"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert got.returncode == 1, (got.returncode, got.stdout[-400:], got.stderr[-400:])
    assert got.stderr.startswith("tmp-capacity: REFUSING to start"), got.stderr[-600:]
    assert "ci-runner:" not in got.stdout, "the runner got past the refusal: %s" % got.stdout[-400:]
    # `--list` only prints, so it is the one mode that does not probe; the same plant must not stop it.
    listed = subprocess.run(
        [
            "npx",
            "--no-install",
            "tsx",
            "scripts/ci-runner/run.ts",
            "--list",
            "--only",
            "check:ci-npmrc",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert listed.returncode == 0, listed.stderr[-400:]
    assert "check:ci-npmrc" in listed.stdout, listed.stderr[-400:]
