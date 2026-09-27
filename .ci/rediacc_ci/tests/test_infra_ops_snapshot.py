"""Unit tests for `rediacc_ci.infra.ops_snapshot`.

No differential: this module's bash twin (`.ci/scripts/test/ops-snapshot.sh`) was added and deleted inside the same task -- ruling 7 refuses new bash under `.ci` -- so there is no recorded corpus and no ledger. These tests drive the module directly, against tmp files standing in for `$GITHUB_OUTPUT`/`$GITHUB_STEP_SUMMARY`/`$RUNNER_TEMP`, and recording fakes standing in for `renet`, `git` and `npx`. No real VM is ever touched: every case that would reach one is a case where the fake stands in for it.
"""

from __future__ import annotations

import os
import pathlib
import re
import stat

import pytest

from rediacc_ci.infra import ops_snapshot as subject

FAKE_GIT = """#!/usr/bin/env python3
import os
import sys

argv = sys.argv[1:]
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a") as fh:
        fh.write("git\\t" + "\\t".join(argv) + "\\n")
if argv[:2] == ["-C", "private/renet"] and argv[2:4] == ["rev-parse", "--short=12"]:
    rc = int(os.environ.get("FAKE_GIT_REV_RC", "0"))
    if rc:
        sys.exit(rc)
    sys.stdout.write(os.environ.get("FAKE_GIT_SHA", "abc123def456") + "\\n")
    sys.exit(0)
sys.exit(0)
"""

FAKE_RENET = """#!/usr/bin/env python3
import os
import sys

argv = sys.argv[1:]
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a") as fh:
        fh.write("renet\\t" + "\\t".join(argv) + "\\n")
sub = argv[2] if len(argv) > 2 else ""
if sub == "key":
    rc = int(os.environ.get("FAKE_RENET_KEY_RC", "0"))
    if rc:
        sys.exit(rc)
    sys.stdout.write(os.environ.get("FAKE_RENET_KEY_STDOUT", "fixture-key"))
    sys.exit(0)
if sub == "restore":
    sys.exit(int(os.environ.get("FAKE_RENET_RESTORE_RC", "0")))
if sub == "save":
    sys.exit(int(os.environ.get("FAKE_RENET_SAVE_RC", "0")))
sys.exit(1)
"""

FAKE_NPX = """#!/usr/bin/env python3
import os
import sys

log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a") as fh:
        fh.write("npx\\t" + "\\t".join(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("FAKE_NPX_RC", "0")))
"""


def _write_fake(path: pathlib.Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture(autouse=True)
def _restore_cwd():
    """`main()` chdirs to the repo root; nothing here may leak that into another test."""
    cwd = os.getcwd()
    yield
    os.chdir(cwd)


@pytest.fixture
def fake_bin(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """`git` and `npx`, resolved through `require_cmd`'s `shutil.which`, prepended to PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _write_fake(bindir / "git", FAKE_GIT)
    _write_fake(bindir / "npx", FAKE_NPX)
    monkeypatch.setenv("PATH", "%s:%s" % (bindir, os.environ.get("PATH", "/usr/bin:/bin")))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    return bindir


@pytest.fixture
def fake_renet(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """`RENET` is a hardcoded absolute path in the subject, not PATH-resolved, so the fixture patches the module constant directly rather than PATH."""
    renet = tmp_path / "renet-bin" / "renet"
    renet.parent.mkdir(parents=True, exist_ok=True)
    _write_fake(renet, FAKE_RENET)
    monkeypatch.setattr(subject, "RENET", str(renet))
    return renet


@pytest.fixture
def io(tmp_path: pathlib.Path) -> subject.Outputs:
    output = tmp_path / "github-output"
    summary = tmp_path / "github-summary"
    output.write_text("", encoding="utf-8")
    summary.write_text("", encoding="utf-8")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    return subject.Outputs("workers", str(output), str(summary), str(runner_temp))


def calls_log(tmp_path: pathlib.Path) -> list[str]:
    log = tmp_path / "calls.log"
    if not log.exists():
        return []
    return [line for line in log.read_text(encoding="utf-8").splitlines() if line]


# --------------------------------------------------------------------------- Outputs: the three files a workflow step hands this program ---------------------------------------------------------------------------


def test_out_appends_lines(tmp_path: pathlib.Path) -> None:
    output = tmp_path / "out"
    output.write_text("", encoding="utf-8")
    o = subject.Outputs("workers", str(output), str(tmp_path / "summary"), str(tmp_path))
    o.out("a=1")
    o.out("b=2")
    assert output.read_text(encoding="utf-8") == "a=1\nb=2\n"


def test_note_prints_and_appends_once_each(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary"
    summary.write_text("", encoding="utf-8")
    o = subject.Outputs("ceph", str(tmp_path / "out"), str(summary), str(tmp_path))
    o.note("hello")
    assert capsys.readouterr().out == "ops-snapshot ceph: hello\n"
    assert summary.read_text(encoding="utf-8") == "ops-snapshot ceph: hello\n"


# --------------------------------------------------------------------------- _du_sh ---------------------------------------------------------------------------


def test_du_sh_reports_a_real_directory(tmp_path: pathlib.Path) -> None:
    (tmp_path / "f").write_text("x" * 1000, encoding="utf-8")
    size = subject._du_sh(tmp_path)
    assert size != ""
    assert "\t" not in size


def test_du_sh_is_empty_for_a_path_that_does_not_exist(tmp_path: pathlib.Path) -> None:
    assert subject._du_sh(tmp_path / "does-not-exist") == ""


# --------------------------------------------------------------------------- key ---------------------------------------------------------------------------


def test_key_is_off_by_default(io: subject.Outputs, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPS_SNAPSHOT", raising=False)
    assert subject.key_cmd(io) == 0
    assert re.search(
        r"^t0=\d+$", pathlib.Path(io.output_path).read_text(encoding="utf-8"), re.MULTILINE
    )
    assert "off (OPS_SNAPSHOT=unset); normal preparation" in pathlib.Path(
        io.summary_path
    ).read_text(encoding="utf-8")
    assert "key=" not in pathlib.Path(io.output_path).read_text(encoding="utf-8")


def test_key_is_off_for_any_value_but_on(
    io: subject.Outputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPS_SNAPSHOT", "off")
    assert subject.key_cmd(io) == 0
    assert "off (OPS_SNAPSHOT=off); normal preparation" in pathlib.Path(io.summary_path).read_text(
        encoding="utf-8"
    )


def test_key_on_without_git_refuses(
    io: subject.Outputs,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPS_SNAPSHOT", "on")
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    assert subject.key_cmd(io) == 1
    assert "git" in capsys.readouterr().err


def test_key_on_with_no_cached_snapshot(
    io: subject.Outputs,
    monkeypatch: pytest.MonkeyPatch,
    fake_bin: pathlib.Path,
    fake_renet: pathlib.Path,
) -> None:
    del fake_bin, fake_renet  # fixtures wire PATH/RENET as a side effect; not referenced by name
    monkeypatch.setenv("OPS_SNAPSHOT", "on")
    monkeypatch.setenv("FAKE_RENET_KEY_RC", "1")
    assert subject.key_cmd(io) == 0
    summary = pathlib.Path(io.summary_path).read_text(encoding="utf-8")
    assert "no key (renet's reason is above" in summary
    assert "key=" not in pathlib.Path(io.output_path).read_text(encoding="utf-8")


def test_key_on_with_a_cached_snapshot_writes_key_and_enabled(
    io: subject.Outputs,
    monkeypatch: pytest.MonkeyPatch,
    fake_bin: pathlib.Path,
    fake_renet: pathlib.Path,
) -> None:
    del fake_bin, fake_renet  # fixtures wire PATH/RENET as a side effect; not referenced by name
    monkeypatch.setenv("OPS_SNAPSHOT", "on")
    monkeypatch.setenv("FAKE_RENET_KEY_STDOUT", "abcd1234")
    monkeypatch.setenv("FAKE_GIT_SHA", "deadbeef0000")
    assert subject.key_cmd(io) == 0
    output = pathlib.Path(io.output_path).read_text(encoding="utf-8")
    lines = output.splitlines()
    assert any(
        re.match(r"^key=ops-snapshot-abcd1234-deadbeef0000-\d{4}-\d{2}$", line) for line in lines
    ), output
    assert "enabled=true" in lines


def test_key_on_propagates_a_failing_git_rev_parse(
    io: subject.Outputs,
    monkeypatch: pytest.MonkeyPatch,
    fake_bin: pathlib.Path,
    fake_renet: pathlib.Path,
) -> None:
    del fake_bin, fake_renet  # fixtures wire PATH/RENET as a side effect; not referenced by name
    monkeypatch.setenv("OPS_SNAPSHOT", "on")
    monkeypatch.setenv("FAKE_GIT_REV_RC", "7")
    assert subject.key_cmd(io) == 7
    assert "key=" not in pathlib.Path(io.output_path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- restore ---------------------------------------------------------------------------


def test_restore_success_writes_ready(
    io: subject.Outputs, fake_renet: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    del fake_renet, tmp_path  # the fixture wires RENET as a side effect; not referenced by name
    assert subject.restore_cmd(io, "1000") == 0
    output = pathlib.Path(io.output_path).read_text(encoding="utf-8")
    assert "ready=true" in output
    summary = pathlib.Path(io.summary_path).read_text(encoding="utf-8")
    assert "cache hit, restored" in summary


def test_restore_failure_warns_and_does_not_fail_the_job(
    io: subject.Outputs,
    monkeypatch: pytest.MonkeyPatch,
    fake_renet: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake_renet  # the fixture wires RENET as a side effect; not referenced by name
    monkeypatch.setenv("FAKE_RENET_RESTORE_RC", "1")
    assert subject.restore_cmd(io, "1000") == 0
    assert "::warning title=ops snapshot::restore failed" in capsys.readouterr().out
    assert "ready=true" not in pathlib.Path(io.output_path).read_text(encoding="utf-8")
    assert "cache hit, restore-failed" in pathlib.Path(io.summary_path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- prepare ---------------------------------------------------------------------------


@pytest.fixture
def e2e_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """`prepare` resolves its playwright cwd from `paths.repo_root()`; point that at a scratch tree."""
    e2e = tmp_path / "packages" / "e2e-tests"
    e2e.mkdir(parents=True)
    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    return e2e


def test_prepare_without_npx_refuses(
    io: subject.Outputs,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    assert subject.prepare_cmd(io, None) == 1
    assert "npx" in capsys.readouterr().err


def test_prepare_success_saves_the_snapshot(
    io: subject.Outputs,
    fake_bin: pathlib.Path,
    fake_renet: pathlib.Path,
    e2e_dir: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    del fake_bin, fake_renet, e2e_dir  # fixtures wire PATH/RENET/cwd as a side effect
    assert subject.prepare_cmd(io, None) == 0
    output = pathlib.Path(io.output_path).read_text(encoding="utf-8")
    assert "ready=true" in output
    summary = pathlib.Path(io.summary_path).read_text(encoding="utf-8")
    assert "cache miss; prepare" in summary
    assert ", saved in" in summary
    calls = calls_log(tmp_path)
    npx_call = next(c for c in calls if c.startswith("npx\t"))
    assert "--config" not in npx_call
    assert "--pass-with-no-tests" in npx_call


def test_prepare_passes_the_config_flag_first(
    io: subject.Outputs,
    fake_bin: pathlib.Path,
    fake_renet: pathlib.Path,
    e2e_dir: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    del fake_bin, fake_renet, e2e_dir  # fixtures wire PATH/RENET/cwd as a side effect
    assert subject.prepare_cmd(io, "playwright.ceph.config.ts") == 0
    calls = calls_log(tmp_path)
    npx_call = next(c for c in calls if c.startswith("npx\t")).split("\t")
    assert npx_call[1:3] == ["playwright", "test"]
    assert npx_call[3:5] == ["--config", "playwright.ceph.config.ts"]


def test_prepare_failure_warns_and_does_not_call_renet(
    io: subject.Outputs,
    monkeypatch: pytest.MonkeyPatch,
    fake_bin: pathlib.Path,
    fake_renet: pathlib.Path,
    e2e_dir: pathlib.Path,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake_bin, fake_renet, e2e_dir  # fixtures wire PATH/RENET/cwd as a side effect
    monkeypatch.setenv("FAKE_NPX_RC", "1")
    assert subject.prepare_cmd(io, None) == 0
    assert "::warning title=ops snapshot::preparation failed" in capsys.readouterr().out
    assert "cache miss, prepare failed after" in pathlib.Path(io.summary_path).read_text(
        encoding="utf-8"
    )
    assert calls_log(tmp_path) == [c for c in calls_log(tmp_path) if not c.startswith("renet\t")]
    assert "ready=true" not in pathlib.Path(io.output_path).read_text(encoding="utf-8")


def test_prepare_save_failure_warns_but_still_reports_the_prepare_time(
    io: subject.Outputs,
    monkeypatch: pytest.MonkeyPatch,
    fake_bin: pathlib.Path,
    fake_renet: pathlib.Path,
    e2e_dir: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del fake_bin, fake_renet, e2e_dir  # fixtures wire PATH/RENET/cwd as a side effect
    monkeypatch.setenv("FAKE_RENET_SAVE_RC", "1")
    assert subject.prepare_cmd(io, None) == 0
    assert "::warning title=ops snapshot::save failed" in capsys.readouterr().out
    summary = pathlib.Path(io.summary_path).read_text(encoding="utf-8")
    assert "save-failed" in summary
    assert "ready=true" not in pathlib.Path(io.output_path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- main: argument handling and dispatch ---------------------------------------------------------------------------


def test_main_requires_at_least_two_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert subject.main([]) == 1
    assert "usage" in capsys.readouterr().err
    assert subject.main(["key"]) == 1


def test_main_requires_runner_temp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    assert subject.main(["key", "workers"]) == 1
    assert "RUNNER_TEMP" in capsys.readouterr().err


def test_main_rejects_an_unknown_subcommand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    assert subject.main(["bogus", "workers"]) == 2
    assert "usage" in capsys.readouterr().err


def test_main_restore_requires_a_third_argument(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    assert subject.main(["restore", "workers"]) == 1
    assert "usage" in capsys.readouterr().err


def test_main_dispatches_key(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setattr(subject.paths, "repo_root", lambda: tmp_path)
    monkeypatch.delenv("OPS_SNAPSHOT", raising=False)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    out = tmp_path / "out"
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert subject.main(["key", "workers"]) == 0
    assert "t0=" in out.read_text(encoding="utf-8")
