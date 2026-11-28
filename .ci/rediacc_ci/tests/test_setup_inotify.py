"""The inotify-limits setup step: floors, the `--check` row, and the idempotent write, against a fake /proc/sys and a tmp sysctl.d file. Nothing touches the real host."""

from __future__ import annotations

import pathlib

from rediacc_ci.setup import inotify
from rediacc_ci.setup.ctx import Ctx, Result


class FakeCtx(Ctx):
    """A Ctx whose commands are recorded and whose `tee` and `sysctl -w` act on tmp paths."""

    def __init__(self, proc: pathlib.Path, fail: str | None = None):
        super().__init__(root=proc)
        self.fail = fail
        self.proc = proc
        self.calls: list[list[str]] = []
        self.said: list[str] = []

    def step(self, message: str) -> None:
        self.said.append(message)

    def info(self, message: str) -> None:
        self.said.append(message)

    def warn(self, message: str) -> None:
        self.said.append("WARN " + message)

    def say(self, message: str = "") -> None:
        self.said.append(message)

    def run(self, argv, *, timeout=None, stdin_text=None):
        del timeout
        self.calls.append(list(argv))
        if self.fail and self.fail in argv:
            return Result(1, "", "sudo: a password is required")
        if "tee" in argv:
            pathlib.Path(argv[-1]).write_text(stdin_text or "", encoding="utf-8")
        if "sysctl" in argv:
            for pair in argv[argv.index("-w") + 1 :]:
                key, _, value = pair.partition("=")
                _set(self.proc, key, int(value))
        return Result(0, "", "")


def _set(proc: pathlib.Path, key: str, value: int) -> None:
    path = proc / key.replace(".", "/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("%d\n" % value)


def _proc(tmp_path: pathlib.Path, instances: int, watches: int) -> pathlib.Path:
    proc = tmp_path / "proc"
    _set(proc, "fs.inotify.max_user_instances", instances)
    _set(proc, "fs.inotify.max_user_watches", watches)
    return proc


def test_below_floor_reports_exact_fix(tmp_path):
    proc = _proc(tmp_path, 128, 524288)
    assert inotify.below_floor(proc) == {"fs.inotify.max_user_instances": 128}
    row, pending = inotify.check_row(proc, tmp_path / "conf")
    assert pending is True
    assert "BELOW the floor" in row
    assert inotify.fix_command() in row
    assert "fs.inotify.max_user_instances=1024" in inotify.fix_command()


def test_at_floor_is_not_pending(tmp_path):
    proc = _proc(tmp_path, 1024, 524288)
    conf = tmp_path / "conf"
    assert inotify.check_row(proc, conf)[1] is False
    conf.write_text(inotify.conf_text())
    assert inotify.check_row(proc, conf) == ("  inotify     at the floor", False)


def test_ensure_writes_then_is_idempotent(tmp_path):
    proc = _proc(tmp_path, 128, 8192)
    conf = tmp_path / "60-rediacc-inotify.conf"
    ctx = FakeCtx(proc)
    assert inotify.ensure(ctx, proc, conf) == 0
    assert conf.read_text() == inotify.conf_text()
    assert inotify.below_floor(proc) == {}
    assert any("sysctl" in call for call in ctx.calls)
    again = FakeCtx(proc)
    assert inotify.ensure(again, proc, conf) == 0
    assert again.calls == []
    assert again.said == []


def test_ensure_persists_when_live_value_is_fine(tmp_path):
    proc = _proc(tmp_path, 2048, 524288)
    conf = tmp_path / "conf"
    ctx = FakeCtx(proc)
    inotify.ensure(ctx, proc, conf)
    assert conf.exists()
    assert not any("sysctl" in call for call in ctx.calls)


def test_unreadable_proc_is_skipped(tmp_path):
    ctx = FakeCtx(tmp_path / "missing")
    assert inotify.ensure(ctx, tmp_path / "missing", tmp_path / "conf") == 0
    assert ctx.calls == []
    assert inotify.check_row(tmp_path / "missing", tmp_path / "conf")[1] is False


def test_at_floor_without_conf_is_not_pending(tmp_path):
    proc = _proc(tmp_path, 1024, 524288)
    row, pending = inotify.check_row(proc, tmp_path / "absent")
    assert pending is False
    assert "at the floor, not persisted" in row


def test_tee_failure_warns_and_stays_zero(tmp_path):
    proc = _proc(tmp_path, 128, 524288)
    conf = tmp_path / "conf"
    ctx = FakeCtx(proc, fail="tee")
    assert inotify.ensure(ctx, proc, conf) == 0
    assert any(m.startswith("WARN could not write") for m in ctx.said)
    assert inotify.fix_command() in ctx.said
    assert not any("sysctl" in call for call in ctx.calls)
    assert not conf.exists()


def test_sysctl_failure_warns_and_stays_zero(tmp_path):
    proc = _proc(tmp_path, 128, 524288)
    ctx = FakeCtx(proc, fail="sysctl")
    assert inotify.ensure(ctx, proc, tmp_path / "conf") == 0
    assert any(m.startswith("WARN could not apply") for m in ctx.said)
    assert inotify.fix_command() in ctx.said
    assert inotify.below_floor(proc) == {"fs.inotify.max_user_instances": 128}


def test_conf_keeps_a_higher_live_value(tmp_path):
    proc = _proc(tmp_path, 4096, 1000)
    conf = tmp_path / "conf"
    inotify.ensure(FakeCtx(proc), proc, conf)
    text = conf.read_text()
    assert "fs.inotify.max_user_instances = 4096" in text
    assert "fs.inotify.max_user_watches = 524288" in text
    again = FakeCtx(proc)
    inotify.ensure(again, proc, conf)
    assert again.calls == []
