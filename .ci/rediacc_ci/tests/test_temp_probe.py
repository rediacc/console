"""temp_probe: a leaking command exits 1 and names the entry, a clean one exits 0, a TMPDIR-ignoring one exits 1."""

from __future__ import annotations

import datetime
import io
import os
import subprocess
import sys

import pytest

from rediacc_ci.dev import temp_probe


def _py(code):
    return [sys.executable, "-c", code]


def _dirs(tmp_path):
    root = tmp_path / "root"
    base = tmp_path / "base"
    root.mkdir()
    base.mkdir()
    return root, base


def test_leaking_command_exits_1_and_names_the_entry(tmp_path):
    root, base = _dirs(tmp_path)
    code = "import os;open(os.path.join(os.environ['TMPDIR'],'leaky-1'),'w').close()"
    status, lines = temp_probe.probe(_py(code), watched=[root], base=base)
    assert status == 1
    assert any("leaky-1" in line and "leaked in TMPDIR" in line for line in lines)


def test_clean_command_exits_0(tmp_path):
    root, base = _dirs(tmp_path)
    status, lines = temp_probe.probe(_py("pass"), watched=[root], base=base)
    assert status == 0
    assert "clean" in lines[0]


def test_control_with_the_leak_removed_exits_0(tmp_path):
    root, base = _dirs(tmp_path)
    code = (
        "import os;p=os.path.join(os.environ['TMPDIR'],'leaky-1');open(p,'w').close();os.remove(p)"
    )
    status, _ = temp_probe.probe(_py(code), watched=[root], base=base)
    assert status == 0


def test_write_outside_tmpdir_exits_1_ignored_tmpdir(tmp_path):
    root, base = _dirs(tmp_path)
    code = f"open({str(root / 'stray-9')!r},'w').close()"
    status, lines = temp_probe.probe(_py(code), watched=[root], base=base)
    assert status == 1
    assert any(temp_probe.IGNORED in line and "stray-9" in line for line in lines)


def test_command_failure_without_leak_keeps_its_status(tmp_path):
    root, base = _dirs(tmp_path)
    status, _ = temp_probe.probe(_py("raise SystemExit(7)"), watched=[root], base=base)
    assert status == 7


def test_probe_removes_only_its_own_fresh_dir(tmp_path):
    root, base = _dirs(tmp_path)
    keep = root / "preexisting-1"
    keep.mkdir()
    temp_probe.probe(_py("pass"), watched=[root], base=base)
    assert keep.is_dir()
    assert os.listdir(base) == []


def test_tmpdir_is_fresh_and_private(tmp_path):
    root, base = _dirs(tmp_path)
    marker = tmp_path / "mode.txt"
    code = f"import os,stat;d=os.environ['TMPDIR'];open({str(marker)!r},'w').write(oct(stat.S_IMODE(os.stat(d).st_mode))+' '+str(len(os.listdir(d))))"
    temp_probe.probe(_py(code), watched=[root], base=base)
    assert marker.read_text() == "0o700 0"


def test_prefix_of():
    assert temp_probe.prefix_of("elite-Ab12Cd") == "elite-"
    assert temp_probe.prefix_of("rediacc-pytest-x1y2") == "rediacc-pytest-"
    assert temp_probe.prefix_of("check-source-rules-q9") == "check-source-rules-"
    assert temp_probe.prefix_of("renet-markers-123456") == "renet-markers-"


def test_census_groups_by_prefix_with_count_and_inodes(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    for name in ("elite-a1", "elite-b2"):
        (root / name).mkdir()
        (root / name / "f").write_text("x")
    (root / "inbox-c3").mkdir()
    groups = temp_probe.census(watched=[root], today_only=True)
    assert groups["elite-"]["count"] == 2
    assert groups["elite-"]["inodes"] == 4
    assert groups["inbox-"]["count"] == 1


def test_census_today_only_skips_old_entries(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    old = root / "elite-a1"
    old.mkdir()
    os.utime(old, (1, 1))
    assert temp_probe.census(watched=[root], today_only=True) == {}
    assert "elite-" in temp_probe.census(watched=[root], today_only=False)


def test_census_now_selects_the_counted_date(tmp_path):
    """Review 6a8068dc.2: an entry dated 2001-06-15 is counted with `now` on that date and skipped the day after, so `now` really selects."""
    root = tmp_path / "root"
    root.mkdir()
    dated = root / "elite-a1"
    dated.mkdir()
    noon = datetime.datetime(2001, 6, 15, 12, 0).astimezone().timestamp()
    os.utime(dated, (noon, noon))
    day = temp_probe._local_date(noon)
    assert "elite-" in temp_probe.census(watched=[root], today_only=True, now=day)
    assert (
        temp_probe.census(watched=[root], today_only=True, now=day + datetime.timedelta(days=1))
        == {}
    )


def _git_repo(path, files):
    path.mkdir()
    for name, text in files.items():
        (path / name).write_text(text, encoding="utf-8")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, env=env)
    subprocess.run(["git", "add", "--", *files], cwd=path, check=True, env=env)
    return path


def test_source_of_names_the_files_carrying_the_prefix(tmp_path):
    """Review 6a8068dc.1: the prefix maps to the tracked files naming it, at most three, and to `-` when none does."""
    repo = _git_repo(
        tmp_path / "repo",
        {
            "a.py": "run_dir('elite-')\n",
            "b.py": "x = 'elite-'\n",
            "c.py": "'elite-'\n",
            "d.py": "'elite-'\n",
            "e.py": "nothing\n",
        },
    )
    assert temp_probe.source_of("elite-", cwd=repo) == "a.py, b.py, c.py"
    assert temp_probe.source_of("inbox-", cwd=repo) == "-"


def test_census_cli_prints_rows_and_sources(tmp_path, monkeypatch):
    """The census branch of `main`: the header, one row per prefix ordered by size, the source column from `source_of`, and `-` under `--no-source`."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "elite-a1").mkdir()
    (root / "elite-a1" / "f").write_text("x" * 9000)
    (root / "inbox-c3").mkdir()
    repo = _git_repo(tmp_path / "repo", {"maker.py": "run_dir('elite-')\n"})
    monkeypatch.setattr(temp_probe, "roots", lambda _environ=None: [root])
    monkeypatch.chdir(repo)
    out = io.StringIO()
    assert temp_probe.main(["census", "--all"], out=out) == 0
    lines = out.getvalue().splitlines()
    assert lines[0].split() == ["prefix", "count", "size", "inodes", "source"]
    assert lines[1].split()[0] == "elite-"
    assert lines[1].endswith("maker.py")
    assert lines[2].split()[0] == "inbox-"
    assert lines[2].endswith("-")
    out = io.StringIO()
    assert temp_probe.main(["census", "--all", "--no-source"], out=out) == 0
    assert out.getvalue().splitlines()[1].endswith("  -")


def test_probe_removes_a_read_only_subdirectory_it_left(tmp_path):
    """Review 6a8068dc.3: a command that leaves a read-only subdirectory with a file in it still leaves no fresh directory behind."""
    root, base = _dirs(tmp_path)
    code = (
        "import os;d=os.path.join(os.environ['TMPDIR'],'ro');os.mkdir(d);"
        "open(os.path.join(d,'f'),'w').close();os.chmod(d,0o500)"
    )
    status, lines = temp_probe.probe(_py(code), watched=[root], base=base)
    assert status == 1
    assert any("ro" in line for line in lines)
    assert os.listdir(base) == []


def test_main_usage_names_the_module_invocation(capsys):
    """Review 6a8068dc.4: the usage line names the documented `python3 -m rediacc_ci.dev.temp_probe` form."""
    assert temp_probe.main(["bogus"], out=io.StringIO()) == 2
    err = capsys.readouterr().err
    assert "python3 -m rediacc_ci.dev.temp_probe -- <cmd>" in err


def test_main_usage_error_without_command(capsys):
    assert temp_probe.main([], out=io.StringIO()) == 2
    assert "Usage" in capsys.readouterr().err


def _unremovable(tmp_path, how):
    base = tmp_path / "shared"
    base.mkdir()
    fresh = base / "temp-probe-x"
    fresh.mkdir()
    if how == "locked-parent":
        base.chmod(0o500)
    else:
        fresh.chmod(0o000)
    return base, fresh


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory modes")
@pytest.mark.parametrize("how", ["locked-parent", "locked-fresh"])
def test_probe_never_chmods_the_shared_root_when_its_own_dir_cannot_go(tmp_path, capsys, how):
    """Review 919552d3.1: a failure on the probe's own directory names it on stderr and leaves the shared temp root's mode alone."""
    base, fresh = _unremovable(tmp_path, how)
    before = base.stat().st_mode & 0o777
    try:
        temp_probe._remove_fresh(str(fresh))
        assert base.stat().st_mode & 0o777 == before
        assert str(fresh) in capsys.readouterr().err
    finally:
        base.chmod(0o700)
        fresh.chmod(0o700)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory modes")
def test_control_a_read_only_child_still_gets_its_parent_made_writable(tmp_path, capsys):
    """Control for the test above: below the probe's directory the retry still repairs the mode."""
    fresh = tmp_path / "temp-probe-y"
    child = fresh / "ro"
    child.mkdir(parents=True)
    (child / "f").write_text("")
    child.chmod(0o500)
    temp_probe._remove_fresh(str(fresh))
    assert not fresh.exists()
    assert capsys.readouterr().err == ""


def test_tool_caches_in_tmpdir_do_not_fail_the_probe(tmp_path):
    root, base = _dirs(tmp_path)
    code = (
        "import os;t=os.environ['TMPDIR'];"
        "os.mkdir(os.path.join(t,'node-compile-cache'));"
        "os.mkdir(os.path.join(t,'tsx-%d'%os.getuid()))"
    )
    status, lines = temp_probe.probe(_py(code), watched=[root], base=base)
    assert status == 0
    assert any(temp_probe.TOOL_CACHE in line and "node-compile-cache" in line for line in lines)


def test_control_a_real_leak_beside_tool_caches_still_fails(tmp_path):
    root, base = _dirs(tmp_path)
    code = (
        "import os;t=os.environ['TMPDIR'];"
        "os.mkdir(os.path.join(t,'node-compile-cache'));"
        "open(os.path.join(t,'leaky-2'),'w').close()"
    )
    status, lines = temp_probe.probe(_py(code), watched=[root], base=base)
    assert status == 1
    assert any("leaked in TMPDIR" in line and "leaky-2" in line for line in lines)


def test_foreign_entry_outside_tmpdir_is_reported_without_failing(tmp_path):
    root, base = _dirs(tmp_path)
    foreign = root / "other-session-1"
    code = f"import os;p={str(foreign)!r};open(p,'w').close();os.utime(p,ns=(1,1))"
    status, lines = temp_probe.probe(_py(code), watched=[root], base=base)
    assert status == 0
    assert any(temp_probe.NOT_OURS in line and "other-session-1" in line for line in lines)


def test_tool_cache_outside_tmpdir_is_ignored(tmp_path):
    root, base = _dirs(tmp_path)
    code = f"import os;os.mkdir({str(root / 'tsx-')!r}+str(os.getuid()))"
    status, lines = temp_probe.probe(_py(code), watched=[root], base=base)
    assert status == 0
    assert any(temp_probe.TOOL_CACHE in line for line in lines)
