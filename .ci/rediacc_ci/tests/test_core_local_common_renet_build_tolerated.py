"""`./rdc.sh` does not fail a read-only command on a broken renet build (#680c2665).

On 2026-11-06 one uncommitted broken file from another session (`pkg/compose/stderr_tail.go: undefined: errors`) failed every `./rdc.sh` command with "renet build failed", read-only `term connect` included. `renet_build_tolerated` decides from the command line, and `prepare_cli` falls back to the last built `bin/renet` for a read-only one while a mutating one keeps failing.
"""

import pytest

from rediacc_ci.core import local_common


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--help"],
        ["--version"],
        ["term", "connect", "box"],
        ["--dev", "term", "connect", "box"],
        ["--config", "bench", "status"],
        ["-o", "json", "machine", "status", "m1"],
        ["machine", "health", "m1"],
        ["job", "list"],
        ["--lang", "de", "status"],
        ["--config=bench", "status"],
    ],
)
def test_read_only_command_lines_tolerate_a_build_failure(argv):
    assert local_common.renet_build_tolerated(argv) is True


@pytest.mark.parametrize(
    "argv",
    [
        ["repo", "sync", "upload", "box"],
        ["machine", "setup", "m1"],
        ["machine", "provision", "m1"],
        ["--dev", "repo", "up", "box"],
        ["--config", "term", "repo", "up", "box"],
        ["machine"],
        ["job", "cancel", "j1"],
        ["--region", "term", "repo", "up", "box"],
        ["--unknown-flag", "status"],
    ],
)
def test_mutating_command_lines_keep_failing_on_a_broken_build(argv):
    assert local_common.renet_build_tolerated(argv) is False


def _world(tmp_path, monkeypatch, *, binary):
    monkeypatch.setenv("LOCAL_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(local_common, "prepare_node_deps_packages", lambda _env=None: True)
    monkeypatch.setattr(local_common, "ensure_cli_built", lambda _env=None: True)
    monkeypatch.setattr(local_common, "ensure_renet_built", lambda _env=None: False)
    if binary:
        path = tmp_path / "private" / "renet" / "bin" / "renet"
        path.parent.mkdir(parents=True)
        path.write_text("last good build")


def test_a_read_only_command_runs_with_the_last_good_renet_and_a_warning(
    tmp_path, monkeypatch, capsys
):
    _world(tmp_path, monkeypatch, binary=True)
    assert local_common.prepare_cli(argv=["term", "connect", "box"]) is True
    assert "renet build failed; this command is read-only" in capsys.readouterr().err


def test_a_mutating_command_fails_on_a_broken_build(tmp_path, monkeypatch):
    _world(tmp_path, monkeypatch, binary=True)
    assert local_common.prepare_cli(argv=["repo", "sync", "upload", "box"]) is False


def test_a_read_only_command_with_no_built_renet_still_fails(tmp_path, monkeypatch):
    _world(tmp_path, monkeypatch, binary=False)
    assert local_common.prepare_cli(argv=["term", "connect", "box"]) is False


def test_a_good_build_is_unchanged(tmp_path, monkeypatch, capsys):
    _world(tmp_path, monkeypatch, binary=False)
    monkeypatch.setattr(local_common, "ensure_renet_built", lambda _env=None: True)
    assert local_common.prepare_cli(argv=["repo", "up", "box"]) is True
    assert capsys.readouterr().err == ""
