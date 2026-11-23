"""Profiler data a machine can act on (agent/plans/PLAN-tooling-speed.md SP5, D6).

Each defect from the plan's Context 9 has a red case and a silent twin:
  * a child of a profiled Python records its own row (the inherited marker used to stand every child down);
  * `PYTHONPATH=.ci python3 -m <module>` records, through the user-site `.pth` loader that bash_env.sh's setup writes (a replaced PYTHONPATH used to drop the recorder), and the loader acts only for a listed repo root;
  * a fixture record is not folded, a lease tree's shape prefix is folded away, and the rollup carries per-day counts and `last_seen`;
  * prune walks every repo folder: a 20-day-old pytest folder goes, a stale lease folder goes, this repo's own folder keeps its rollup, and a RESPROFILE_ROOT fixture never reaches its siblings.

Every child interpreter runs with HOME, PYTHONUSERBASE and TMPDIR inside the test's own directory, so nothing here reads or writes the real ~/.claude/resprofile.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import time

import pytest
import wl_resprofile as R

REPO = pathlib.Path(__file__).resolve().parents[3]
PROFILE = REPO / ".claude" / "hooks" / "profile"
# The interpreter the commands run and pth_setup.sh asks for its user site: python3 on PATH, never this suite's own (a tool venv, where no user site is read).
PY = shutil.which("python3") or "python3"


def child_env(tmp: pathlib.Path, **extra: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("WORKLIST_", "_WL_", "PYTHON", "RESPROFILE", "BASH_ENV"))
    }
    (tmp / "t").mkdir(exist_ok=True)
    env.update(HOME=str(tmp / "home"), PYTHONUSERBASE=str(tmp / "ub"), TMPDIR=str(tmp / "t"))
    env.update(extra)
    return env


def records(tmp: pathlib.Path) -> list[dict]:
    out = []
    for f in sorted((tmp / "home" / ".claude" / "resprofile").glob("*/*/exit.jsonl")):
        out.extend(json.loads(line) for line in f.read_text(encoding="utf-8").splitlines())
    return out


def run_py(tmp, args, **extra):
    return subprocess.run(
        [PY, *args],
        cwd=str(REPO),
        env=child_env(tmp, **extra),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


# ---- the pid-keyed marker -------------------------------------------------------


def test_a_child_of_a_profiled_python_records_its_own_row(tmp_path):
    spawn = "import subprocess, sys; subprocess.run([sys.executable, '-c', 'pass'], check=True)"
    got = run_py(tmp_path, ["-c", spawn], PYTHONPATH=str(PROFILE / "py"))
    assert got.returncode == 0, got.stderr
    assert got.stdout == ""
    assert got.stderr == ""
    rows = records(tmp_path)
    assert len(rows) == 2, rows
    assert all(r["src"] == "site" and r["shape"] == "py:<inline>" for r in rows)


def test_one_process_still_writes_one_row(tmp_path):
    """CONTROL: the marker still stands a second arrival in the same process down."""
    got = run_py(
        tmp_path,
        ["-c", "import importlib; import sitecustomize; importlib.reload(sitecustomize)"],
        PYTHONPATH=str(PROFILE / "py"),
    )
    assert got.returncode == 0, got.stderr
    assert len(records(tmp_path)) == 1


def test_a_hook_process_writes_one_rich_row(tmp_path):
    """wl_resprofile claims THIS process (`super:<pid>`), so the site recorder stands down in it and only the richer row is written; an unkeyed claim wrote both. A second install() in the same process adds no second row."""
    hook = (
        "import sys; sys.path.insert(0, %r); import wl_resprofile; "
        "wl_resprofile.install(); wl_resprofile.install()"
        % str(REPO / ".claude" / "hooks" / "stop")
    )
    got = run_py(tmp_path, ["-c", hook], PYTHONPATH=str(PROFILE / "py"))
    assert got.returncode == 0, got.stderr
    rows = records(tmp_path)
    assert len(rows) == 1, rows
    assert "psi_us" in rows[0]
    assert "src" not in rows[0]


def test_a_child_of_a_hook_process_records_its_own_row(tmp_path):
    """The claim is the parent's: a child python3 of a hook process writes its own site row."""
    hook = (
        "import subprocess, sys; sys.path.insert(0, %r); import wl_resprofile; wl_resprofile.install(); "
        "subprocess.run([sys.executable, '-c', 'pass'], check=True)"
    ) % str(REPO / ".claude" / "hooks" / "stop")
    got = run_py(tmp_path, ["-c", hook], PYTHONPATH=str(PROFILE / "py"))
    assert got.returncode == 0, got.stderr
    rows = records(tmp_path)
    assert sorted(r.get("src", "rich") for r in rows) == ["rich", "site"]


# ---- the .pth loader ------------------------------------------------------------


def setup_pth(tmp, repo=REPO):
    return subprocess.run(
        ["bash", str(PROFILE / "pth_setup.sh"), str(repo)],
        env=child_env(tmp),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def user_site(tmp) -> pathlib.Path:
    got = run_py(tmp, ["-c", "import site; print(site.getusersitepackages())"])
    return pathlib.Path(got.stdout.strip())


def test_a_replaced_pythonpath_records_through_the_pth_loader(tmp_path):
    got = setup_pth(tmp_path)
    assert got.returncode == 0
    assert got.stdout == ""
    assert got.stderr == ""
    site = user_site(tmp_path)
    assert (site / "rediacc_resprofile.pth").read_text() == "import rediacc_resprofile_loader\n"
    assert (site / "rediacc_resprofile_loader.py").read_bytes() == (
        PROFILE / "pth_loader.py"
    ).read_bytes()
    ran = run_py(tmp_path, ["-m", "rediacc_ci.paths"], PYTHONPATH=str(REPO / ".ci"))
    assert ran.returncode == 0, ran.stderr
    assert ran.stderr == ""
    shapes = [r["shape"] for r in records(tmp_path)]
    assert "py:.ci/rediacc_ci/paths.py" in shapes, shapes


def test_without_the_loader_a_replaced_pythonpath_records_nothing(tmp_path):
    """CONTROL: the gap the loader closes. No .pth, PYTHONPATH=.ci: no row."""
    ran = run_py(tmp_path, ["-m", "rediacc_ci.paths"], PYTHONPATH=str(REPO / ".ci"))
    assert ran.returncode == 0, ran.stderr
    assert records(tmp_path) == []


def test_bash_env_writes_the_loader(tmp_path):
    """The setup rides bash_env.sh, so any non-interactive bash of the session installs it (no supervisor binary needed)."""
    got = subprocess.run(
        ["bash", "-c", "true"],
        env=child_env(tmp_path, BASH_ENV=str(PROFILE / "bash_env.sh")),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert got.returncode == 0
    assert got.stdout == ""
    assert got.stderr == ""
    site = user_site(tmp_path)
    assert (site / "rediacc_resprofile.pth").read_text() == "import rediacc_resprofile_loader\n"
    assert (site / "rediacc_resprofile_loader.py").is_file()
    roots = (tmp_path / "home" / ".claude" / "resprofile" / "pth-roots").read_text()
    assert roots.splitlines() == [str(REPO)]


def test_the_setup_is_idempotent_and_off_switch_holds(tmp_path):
    setup_pth(tmp_path)
    setup_pth(tmp_path)
    roots = (tmp_path / "home" / ".claude" / "resprofile" / "pth-roots").read_text()
    assert roots.splitlines() == [str(REPO)]
    off = tmp_path / "off"
    off.mkdir()
    subprocess.run(
        ["bash", "-c", "true"],
        env=child_env(off, BASH_ENV=str(PROFILE / "bash_env.sh"), WORKLIST_PROFILE="off"),
        check=True,
        timeout=60,
    )
    assert not (off / "home" / ".claude" / "resprofile" / "pth-roots").exists()


def load_loader(monkeypatch, tmp_path):
    """pth_loader as a module, with HOME in the test directory (it runs its loader at import)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    spec = importlib.util.spec_from_file_location("_test_pth_loader", PROFILE / "pth_loader.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_loader_acts_only_for_a_listed_root(monkeypatch, tmp_path):
    """A directory anyone can create, holding a recorder at the expected path, is never run unless its root is listed."""
    mod = load_loader(monkeypatch, tmp_path)
    planted = tmp_path / "planted"
    (planted / ".claude/hooks/profile/py").mkdir(parents=True)
    (planted / ".claude/hooks/profile/py/sitecustomize.py").write_text("raise SystemExit(9)\n")
    roots = tmp_path / "roots"
    roots.write_text(str(REPO) + "\n")
    assert mod.recorder_path(str(planted), str(roots)) is None
    assert mod.recorder_path(str(REPO / ".ci"), str(roots)) == str(
        REPO / ".claude/hooks/profile/py/sitecustomize.py"
    )
    roots.write_text("%s\n%s\n" % (REPO, planted))
    assert mod.recorder_path(str(planted), str(roots)) == str(
        planted / ".claude/hooks/profile/py/sitecustomize.py"
    )
    assert mod.recorder_path(str(REPO), str(tmp_path / "absent")) is None


# ---- the fold -------------------------------------------------------------------


def fold_world(tmp_path, monkeypatch, recs):
    monkeypatch.setenv("RESPROFILE_ROOT", str(tmp_path / "rp"))
    day = tmp_path / "rp" / "2026-11-23"
    day.mkdir(parents=True)
    t0 = day / "exit.jsonl"
    t0.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return R.fold((t0, tmp_path / "rp" / "rollup.json"))


def rec(shape, t_ms, **kw):
    return {"v": 1, "t": t_ms, "shape": shape, "cpu_ms": 10, "rss_kb": 1000, **kw}


DAY1 = 1763856000000  # 2025-11-23T00:00:00Z
DAY2 = DAY1 + 86400000


def test_a_fixture_record_is_not_folded(tmp_path, monkeypatch):
    roll = fold_world(
        tmp_path,
        monkeypatch,
        [rec("py:real.py", DAY1, fixture=False), rec("py:fixture.py", DAY1, fixture=True)],
    )
    assert set(roll["shapes"]) == {"py:real.py"}
    assert roll["folded_lines"] == 1
    assert roll["skipped_fixture_lines"] == 1


def test_the_rollup_carries_day_counts_and_last_seen(tmp_path, monkeypatch):
    roll = fold_world(
        tmp_path,
        monkeypatch,
        [rec("py:a.py", DAY1), rec("py:a.py", DAY2), rec("py:a.py", DAY2)],
    )
    ent = roll["shapes"]["py:a.py"]
    assert ent["n"] == 3
    assert ent["days"] == {"2025-11-23": 1, "2025-11-24": 2}
    assert ent["last_seen"] == "2025-11-24"


def test_a_lease_tree_prefix_is_folded_into_one_shape(tmp_path, monkeypatch):
    roll = fold_world(
        tmp_path,
        monkeypatch,
        [
            rec("py:.claude/worktrees/agent-abc/.claude/hooks/stop/wl_core.py", DAY1),
            rec("py:.claude/hooks/stop/wl_core.py", DAY1),
            rec("sh:.claude/worktrees/x1/run.sh", DAY1),
        ],
    )
    assert roll["shapes"]["py:.claude/hooks/stop/wl_core.py"]["n"] == 2
    assert "sh:run.sh" in roll["shapes"]
    assert not any("worktrees" in s for s in roll["shapes"])


def test_day_counts_are_bounded(tmp_path, monkeypatch):
    many = [rec("py:a.py", DAY1 + i * 86400000) for i in range(R.DAYS_KEEP + 5)]
    ent = fold_world(tmp_path, monkeypatch, many)["shapes"]["py:a.py"]
    assert len(ent["days"]) == R.DAYS_KEEP
    assert ent["last_seen"] == max(ent["days"])


# ---- prune ----------------------------------------------------------------------


def _day(days_ago: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - days_ago * 86400))


def _mk(path: pathlib.Path, age_days: int = 0) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "exit.jsonl").write_text("{}\n")
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
        os.utime(path.parent, (old, old))
    return path


def test_prune_walks_every_repo_folder(tmp_path):
    top = tmp_path / "resprofile"
    pytest_old = _mk(top / "tmp-pytest-of-dev-pytest-3-test_x0" / _day(20), 20)
    pytest_new = _mk(top / "home-dev-.cache-tmp-base-pytest-of-dev-pytest-9-gw1" / _day(0))
    mine = top / "home-dev-console"
    mine_old = _mk(mine / _day(20))
    mine_new = _mk(mine / _day(0))
    lease_old = _mk(top / "home-dev-console-.claude-worktrees-agent-old" / _day(20), 20)
    lease_live = _mk(top / "home-dev-console-.claude-worktrees-agent-live" / _day(1))
    stray_old = _mk(top / _day(20))
    stray_new = _mk(top / _day(1))
    got = R.prune_all(top, keep=mine)
    assert not pytest_old.parent.exists()
    assert not pytest_new.parent.exists()
    assert not mine_old.exists()
    assert mine_new.exists()
    assert not lease_old.parent.exists()
    assert lease_live.exists()
    assert not stray_old.exists()
    assert stray_new.exists()
    assert got == {"tmp": 2, "stale": 1, "days": 2, "errors": 0}


def test_this_repos_folder_keeps_its_rollup_with_no_day_left(tmp_path):
    top = tmp_path / "resprofile"
    mine = top / "home-dev-console"
    _mk(mine / _day(20), 20)
    (mine / "rollup.json").write_text("{}")
    old = time.time() - 30 * 86400
    os.utime(mine, (old, old))
    R.prune_all(top, keep=mine)
    assert (mine / "rollup.json").exists()


def test_a_fixture_root_never_reaches_its_siblings(tmp_path, monkeypatch):
    sibling = _mk(tmp_path / "tmp-pytest-of-sibling" / _day(20), 20)
    monkeypatch.setenv("RESPROFILE_ROOT", str(tmp_path / "rp"))
    assert R.prune_top() is None
    got = R.prune_all_daily()
    assert got == {"tmp": 0, "stale": 0, "days": 0, "errors": 0}
    assert sibling.exists()


def test_the_walk_runs_once_a_day(tmp_path):
    top = tmp_path / "resprofile"
    _mk(top / "tmp-pytest-of-a" / _day(0))
    assert R.prune_all_daily(top) == {"tmp": 1, "stale": 0, "days": 0, "errors": 0}
    _mk(top / "tmp-pytest-of-b" / _day(0))
    assert R.prune_all_daily(top) is None
    assert (top / "tmp-pytest-of-b").exists()


@pytest.mark.parametrize(
    ("shape", "want"),
    [
        ("py:.claude/worktrees/a/x.py", "py:x.py"),
        ("py:x.py", "py:x.py"),
        ("py:<external>", "py:<external>"),
        ("py:docs/.claude/worktrees/a/x.py", "py:docs/.claude/worktrees/a/x.py"),
    ],
)
def test_canonical_shape(shape, want):
    assert R.canonical_shape(shape) == want
