"""temp_probe: a leaking command exits 1 and names the entry, a clean one exits 0, a TMPDIR-ignoring one exits 1."""

from __future__ import annotations

import datetime
import io
import os
import sys

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
    tomorrow = temp_probe._local_date(None) + datetime.timedelta(days=1)
    assert temp_probe.census(watched=[root], today_only=True, now=tomorrow) == {}


def test_main_usage_error_without_command(capsys):
    assert temp_probe.main([], out=io.StringIO()) == 2
    assert "Usage" in capsys.readouterr().err
