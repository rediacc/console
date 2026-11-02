"""Leg-dependency refusals of the backup drill: the suggestion each prints, and that they run before any preflight or setup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from rediacc_ci.drills import backup
from rediacc_ci.well_known import ACCOUNT_DEV_PORT

if TYPE_CHECKING:
    import pathlib

SETUP = (
    "preflight_tools",
    "preflight_machines",
    "announce_unrunnable",
    "setup_sandbox",
    "setup_store_env",
    "setup_gateway",
    "setup_store_bucket",
    "setup_account",
    "setup_renet",
)


@pytest.fixture
def subject(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> backup.Backup:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    (root / ".account-state").write_text(f"gateway_port={ACCOUNT_DEV_PORT}\nstarted=1\n")
    drill = backup.BackupDrill("backup", selftest=False, keep_work=False)
    drill.init()
    sub = backup.Backup(drill, backup.Options())
    monkeypatch.setattr(sub, "announce_cost", lambda: None)
    monkeypatch.setattr(drill, "selftest_probe", lambda: None)
    return sub


def _arm(subject: backup.Backup, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    called: list[str] = []
    for name in SETUP:
        monkeypatch.setattr(subject, name, lambda n=name: called.append(n))
    return called


def test_legs_with_names_each_leg_once_and_keeps_order() -> None:
    opts = backup.Options()
    opts.legs = "a,o,o"
    assert opts.legs_with("a", "b") == "a,b,o"
    opts.legs = "o,c,c"
    assert opts.legs_with("a") == "a,o,c"


def test_refuses_plane_legs_without_leg_a_before_any_setup(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    called = _arm(subject, monkeypatch)
    subject.o.legs = "b,b"
    with pytest.raises(SystemExit) as exc:
        subject.run_all()
    assert exc.value.code == 1
    assert called == []
    err = capsys.readouterr().err
    assert "--legs a,b" in err
    assert "a,b,b" not in err


def test_refuses_leg_o_without_leg_b_before_any_setup(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    called = _arm(subject, monkeypatch)
    subject.o.legs = "a,o"
    with pytest.raises(SystemExit) as exc:
        subject.run_all()
    assert exc.value.code == 1
    assert called == []
    err = capsys.readouterr().err
    assert "--legs a,b,o" in err
