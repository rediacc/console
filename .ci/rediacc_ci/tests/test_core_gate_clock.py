"""`rediacc_ci.core.gate_clock`, and the five clock gates that read it (nightly-green F1).

The seam is `REDIACC_GATE_CLOCK`. A seam that moves "now" can be misused as a skip, so every case here is a PAIR on one fixture: the clock planted PAST the gate's deadline must give RED (rc 1), and the clock planted at today's wall time must give today's verdict (rc 0). A gate that ignored the seam fails the first half; a gate that treated the seam as an excuse fails it too; a gate that was red on the fixture for some other reason fails the second.

The pin-freshness hold expiry is the TypeScript twin (`gateNowMs`) and is exercised by `check:ci-pin-freshness --selftest` (the three `CLOCK` controls), not here.

Fixtures are built here and the gates run against them; `secret-reachability` and `runner-advice` read tracked files that a fixture can supply only through seams, so they run over the real tree (read-only, sub-second) and over the runner-advice fixture helpers of its own gate test.
"""

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import gate_clock
from rediacc_ci.quality import plan_housekeeping as hk
from rediacc_ci.quality import secret_reachability as sr
from rediacc_ci.tests.gates import harness
from rediacc_ci.tests.gates import test_gate_runner_advice as ra

PAST_EVERY_DEADLINE = "2035-01-01"


def _wall() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _env(**over: str) -> dict[str, str]:
    return {"PYTHONPATH": str(paths.from_root(".ci")), gate_clock.TEST_ENV: "1", **over}


@pytest.fixture(autouse=True)
def _harness_marked(monkeypatch):
    """This file IS the test harness: the marker is set and CI is cleared (CI=true refuses the seam), in-process and in every child."""
    monkeypatch.setenv(gate_clock.TEST_ENV, "1")
    monkeypatch.delenv("CI", raising=False)


# --------------------------------------------------------------------------- The module itself.


def test_unset_and_blank_read_the_wall_clock(monkeypatch):
    monkeypatch.delenv(gate_clock.ENV, raising=False)
    assert abs((gate_clock.now() - _wall()).total_seconds()) < 5
    monkeypatch.setenv(gate_clock.ENV, "   ")
    assert abs((gate_clock.now() - _wall()).total_seconds()) < 5


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("2027-01-01", dt.datetime(2027, 1, 1, tzinfo=dt.UTC)),
        ("2027-01-01T06:30:00", dt.datetime(2027, 1, 1, 6, 30, tzinfo=dt.UTC)),
        ("2027-01-01T06:30:00Z", dt.datetime(2027, 1, 1, 6, 30, tzinfo=dt.UTC)),
        ("2027-01-01T08:30:00+02:00", dt.datetime(2027, 1, 1, 6, 30, tzinfo=dt.UTC)),
    ],
)
def test_a_planted_clock_is_read_as_utc(monkeypatch, raw, want):
    monkeypatch.setenv(gate_clock.ENV, raw)
    assert gate_clock.now() == want
    assert gate_clock.today() == want.date()


@pytest.mark.parametrize("raw", ["tomorrow", "2027-13-45", "1700000000"])
def test_a_bad_value_is_a_failure_and_never_the_wall_clock(monkeypatch, raw):
    monkeypatch.setenv(gate_clock.ENV, raw)
    with pytest.raises(gate_clock.GateClockError, match="REDIACC_GATE_CLOCK"):
        gate_clock.now()


def test_a_planted_clock_says_so_on_stderr(monkeypatch, capsys):
    gate_clock._announced.clear()
    monkeypatch.setenv(gate_clock.ENV, "2031-02-03")
    gate_clock.now()
    gate_clock.now()
    err = capsys.readouterr().err
    assert err.count("REDIACC_GATE_CLOCK=2031-02-03") == 1, err


# --------------------------------------------------------------------------- plan-housekeeping.


def _hk_tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """Three plans last committed two days ago: inside the 33-day window today."""
    tree = tmp_path / "hk"
    (tree / "agent").mkdir(parents=True)
    (tree / ".ci" / "config").mkdir(parents=True)
    (tree / ".ci" / "config" / "plan-lifecycle.json").write_text(
        '{"plan_globs": ["agent/PLAN-*.md", "agent/plans/PLAN-*.md"], "stub_status": "moved",'
        ' "warn_days": 26, "delete_days": 33, "record_states": ["compacted", "parked"]}\n',
        encoding="utf-8",
    )
    for name in "abc":
        (tree / "agent" / f"PLAN-{name}.md").write_text(f"# {name}\nStatus: draft\n")
    when = (_wall() - dt.timedelta(days=2)).isoformat()
    ident = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_DATE": when,
        "GIT_AUTHOR_DATE": when,
    }
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-q", "--no-gpg-sign", "-m", "plans"]):
        done = subprocess.run(
            ["git", "-C", str(tree), *argv],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, **ident},
        )
        assert done.returncode == 0, done.stderr
    return tree


def _hk_run(tree: pathlib.Path, clock: str) -> subprocess.CompletedProcess:
    env = _env(
        **{
            hk.ROOT_ENV: str(tree),
            hk.CONFIG_ENV: str(tree / ".ci" / "config" / "plan-lifecycle.json"),
            hk.ALLOWLIST_ENV: str(tree / "no-allowlist"),
            hk.MIN_FILES_ENV: "3",
            gate_clock.ENV: clock,
        }
    )
    argv = harness.without_controls([sys.executable, "-m", "rediacc_ci.quality.plan_housekeeping"])
    return subprocess.run(
        argv, capture_output=True, text=True, check=False, env={**os.environ, **env}, cwd=tree
    )


def test_plan_housekeeping_reds_on_a_clock_past_the_delete_window(tmp_path):
    tree = _hk_tree(tmp_path)
    today = _hk_run(tree, _wall().isoformat())
    assert today.returncode == 0, today.stdout + today.stderr
    planted = _hk_run(tree, PAST_EVERY_DEADLINE)
    assert planted.returncode == 1, planted.stdout + planted.stderr
    assert "agent/PLAN-a.md" in planted.stdout + planted.stderr


def test_plan_housekeeping_age_reads_the_seam(monkeypatch):
    stamp = (_wall() - dt.timedelta(days=2)).isoformat()
    monkeypatch.delenv(gate_clock.ENV, raising=False)
    assert hk.age_days(stamp) == 2
    monkeypatch.setenv(gate_clock.ENV, PAST_EVERY_DEADLINE)
    assert hk.age_days(stamp) > 33


# --------------------------------------------------------------------------- plan-folders.

PLAN_FOLDERS_SHIM = paths.from_root(".ci", "scripts", "quality", "check_plan_folders.py")


def _pf_tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """22 live plans (the gate's floor is 21) and one finished plan moved ten days ago: inside the 40-day retention today."""
    tree = tmp_path / "pf"
    (tree / ".ci" / "config").mkdir(parents=True)
    shutil.copy(
        paths.from_root(".ci", "config", "plan-lifecycle.json"),
        tree / ".ci" / "config" / "plan-lifecycle.json",
    )
    for i in range(22):
        plan = tree / "agent" / "plans" / f"PLAN-filler-{i:02d}.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(f"# PLAN: filler {i}\nStatus: in-progress\n\n- [ ] a box\n")
    moved = (_wall() - dt.timedelta(days=10)).date().isoformat()
    done = tree / "agent" / "plans" / "_done" / "PLAN-finished.md"
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text(f"# PLAN: finished\nStatus: done\nFirst-Seen: {moved}\n")
    ledger = tree / ".ci" / "config" / "plan-boxes.json"
    ledger.write_text(
        json.dumps({"plans": {"agent/plans/_done/PLAN-finished.md": {"moved_at": moved}}}) + "\n"
    )
    for argv in (
        ["init", "-q", "."],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
        ["add", "-A"],
        ["commit", "-qm", "base"],
    ):
        # F6 compares moved_at with the commit date, so the base commit is dated the day the plan "moved".
        done_run = subprocess.run(
            ["git", "-C", str(tree), *argv],
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": f"{moved}T12:00:00+00:00",
                "GIT_COMMITTER_DATE": f"{moved}T12:00:00+00:00",
            },
        )
        assert done_run.returncode == 0, done_run.stderr
    return tree


def _pf_run(tree: pathlib.Path, clock: str) -> harness.RunResult:
    return harness.run(
        harness.without_controls([sys.executable, str(PLAN_FOLDERS_SHIM)]),
        cwd=paths.repo_root(),
        env={"PLAN_FOLDERS_ROOT": str(tree), gate_clock.ENV: clock},
    )


def test_plan_folders_reds_on_a_clock_past_the_retention(tmp_path):
    tree = _pf_tree(tmp_path)
    today = _pf_run(tree, _wall().isoformat())
    assert today.rc == 0, today.out + today.err
    planted = _pf_run(tree, PAST_EVERY_DEADLINE)
    assert planted.rc == 1, planted.out + planted.err
    assert "F3 agent/plans/_done/PLAN-finished.md" in planted.err, planted.err


# --------------------------------------------------------------------------- runner-advice.


def _ra_run(tmp_path: pathlib.Path, clock: str) -> harness.RunResult:
    """The runner-advice gate's own fixture: `waster` already on slim, the baseline stamped a day ago."""
    ra.workflow(tmp_path / "wf", "ubuntu-slim")
    ra.baseline(tmp_path / "base.json", ra.fresh_stamp())
    (tmp_path / "allow").write_text("", encoding="utf-8")
    return harness.run(
        [sys.executable, str(ra.GATE)],
        env={
            "RUNNER_ADVICE_BASELINE": str(tmp_path / "base.json"),
            "RUNNER_ADVICE_WORKFLOW_DIR": str(tmp_path / "wf"),
            "RUNNER_ADVICE_ALLOWLIST": str(tmp_path / "allow"),
            gate_clock.ENV: clock,
        },
    )


def test_runner_advice_reds_on_a_clock_past_the_baseline_age_limit(tmp_path):
    today = _ra_run(tmp_path, _wall().isoformat())
    assert today.rc == 0, today.out + today.err
    planted = _ra_run(tmp_path, PAST_EVERY_DEADLINE)
    assert planted.rc == 1, planted.out + planted.err
    assert "the baseline itself is stale" in planted.err, planted.err


# --------------------------------------------------------------------------- secret-reachability.


def _sr_run(clock: str) -> harness.RunResult:
    return harness.run(
        [sys.executable, "-m", "rediacc_ci.quality.secret_reachability"],
        cwd=paths.repo_root(),
        env=_env(**{gate_clock.ENV: clock}),
    )


def test_secret_reachability_reds_on_a_clock_past_the_record_age_limit():
    today = _sr_run(_wall().isoformat())
    assert today.rc == 0, today.out + today.err
    planted = _sr_run(PAST_EVERY_DEADLINE)
    assert planted.rc == 1, planted.out + planted.err
    assert "days old" in planted.err, planted.err


def test_secret_reachability_waiver_expiry_reads_the_seam(monkeypatch):
    monkeypatch.setitem(
        sr.KNOWN_UNREACHABLE, ("fixture-repo", "FIXTURE_SECRET"), ("2031-06-01", "x")
    )
    refs = {"fixture-repo": {"FIXTURE_SECRET"}}
    monkeypatch.delenv(gate_clock.ENV, raising=False)
    assert sr.verdicts(refs, {}) == []
    monkeypatch.setenv(gate_clock.ENV, PAST_EVERY_DEADLINE)
    problems = sr.verdicts(refs, {})
    assert len(problems) == 1, problems
    assert "EXPIRED on 2031-06-01" in problems[0], problems
