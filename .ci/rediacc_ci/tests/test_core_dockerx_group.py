"""`dockerx.group_command` and the two Python re-exec sites that use it, with `sg` present and absent.

Ubuntu 26.04 ships no `sg` and its sudo is sudo-rs, so the absent route must name `sudo -n -u <user> env PATH= HOME=` explicitly, and carry every other value in a 0600 file rather than on the argv (review 8abaf8f4.1).
"""

import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import types

import pytest

from rediacc_ci import proc
from rediacc_ci.core import dockerx, local_common
from rediacc_ci.setup import machine
from rediacc_ci.setup.ctx import Ctx

GROUP = "docker:x:999:alice\n"


def _bin(tmp_path: pathlib.Path, *names: str) -> str:
    folder = tmp_path / "bin"
    folder.mkdir(exist_ok=True)
    for name in names:
        tool = folder / name
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    return str(folder)


class _ExecError(Exception):
    def __init__(self, argv: list[str]) -> None:
        super().__init__("exec")
        self.argv = argv


def _raise_exec(argv: list[str], **_: object) -> None:
    raise _ExecError(argv)


@pytest.fixture(autouse=True)
def _private_tmp(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """The environment files land in this test's own directory, not the shared /tmp."""
    folder = tmp_path / "envfiles"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def _env_file(argv: list[str]) -> pathlib.Path:
    return pathlib.Path(argv[-1])


def test_sg_present_keeps_sg(tmp_path: pathlib.Path) -> None:
    env = {"PATH": _bin(tmp_path, "sg", "sudo"), "HOME": "/h"}
    assert dockerx.group_command("run it", user="u", env=env) == ["sg", "docker", "-c", "run it"]


def test_sg_absent_uses_sudo_with_path_and_home(tmp_path: pathlib.Path) -> None:
    env = {"PATH": _bin(tmp_path, "sudo"), "HOME": "/h"}
    argv = dockerx.group_command("run it", user="u", env=env, extra_env={"G": "1"})
    assert argv is not None
    assert argv[:-1] == [
        "sudo",
        "-n",
        "-u",
        "u",
        "env",
        "PATH=%s" % env["PATH"],
        "HOME=/h",
        "bash",
        "-c",
        '. "$1" || { rm -f -- "$1"; exit 126; }; rm -f -- "$1"; shift\nrun it',
        "bash",
    ]
    assert _env_file(argv).read_text() == "export G=1\n"


def test_sudo_route_puts_no_inherited_value_on_the_argv(tmp_path: pathlib.Path) -> None:
    """Review 8abaf8f4.1: any local user reads an argv through /proc/<pid>/cmdline, so a token must travel in the 0600 file, never on the argv."""
    secret = "rdt_planted_secret_value_8abaf8f4"
    env = {"PATH": _bin(tmp_path, "sudo"), "HOME": "/h", "REDIACC_TOKEN": secret}
    argv = dockerx.group_command("run it", user="u", env=env, extra_env={"G": "1"})
    assert argv is not None
    assert not any(secret in word for word in argv)
    assert not any(word.startswith(("REDIACC_TOKEN=", "G=")) for word in argv)
    carried = _env_file(argv)
    assert stat.S_IMODE(carried.stat().st_mode) == 0o600
    assert "export REDIACC_TOKEN=%s\n" % secret in carried.read_text()


def test_sudo_route_keeps_the_rest_of_the_environment_as_sg_does(tmp_path: pathlib.Path) -> None:
    """Review 0ec896a9.1: a token or REDIACC_* setting reaches the re-exec'd run on the sudo route too; an exported function, an odd name or a bash readonly name is not carried."""
    env = {
        "PATH": _bin(tmp_path, "sudo"),
        "HOME": "/h",
        "SCRIPT_ENTRYPOINT": "run.sh",
        "REDIACC_X": "1",
        "BASH_FUNC_f%%": "() { :; }",
        "A-B": "no",
        "SHELLOPTS": "braceexpand",
    }
    argv = dockerx.group_command("run it", user="u", env=env, extra_env={"G": "1"})
    assert argv is not None
    lines = _env_file(argv).read_text().splitlines()
    assert "export SCRIPT_ENTRYPOINT=run.sh" in lines
    assert "export REDIACC_X=1" in lines
    assert lines[-1] == "export G=1"
    assert argv.count("PATH=%s" % env["PATH"]) == 1
    assert not any(line.startswith(("export PATH=", "export HOME=")) for line in lines)
    assert not any(
        line.startswith(("export BASH_FUNC_", "export A-B", "export SHELLOPTS")) for line in lines
    )


def test_child_sees_the_environment_and_removes_the_file(tmp_path: pathlib.Path) -> None:
    """The bash half of the argv, run for real: the child reads a value with spaces and quotes from the file, the file is gone before `command` runs, and `command` sees no positional parameter."""
    value = 'it\'s a "token" $HOME `x`'
    env = {
        "PATH": _bin(tmp_path, "sudo") + os.pathsep + os.environ["PATH"],
        "HOME": "/h",
        "TOK": value,
    }
    argv = dockerx.group_command(
        'printf "%s|%s|%s" "$TOK" "$#" "$G"', user="u", env=env, extra_env={"G": "1"}
    )
    assert argv is not None
    carried = _env_file(argv)
    done = subprocess.run(
        argv[argv.index("bash") :],
        env={"PATH": env["PATH"], "HOME": "/h"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert (done.returncode, done.stderr) == (0, "")
    assert done.stdout == "%s|0|1" % value
    assert not carried.exists()


def test_env_file_is_removed_at_exit_when_the_child_never_ran(tmp_path: pathlib.Path) -> None:
    """A refused `sudo -n` starts no bash, so the probe's file is removed at interpreter exit instead."""
    script = (
        "from rediacc_ci.core import dockerx\n"
        "argv = dockerx.group_command('x', user='u', env={'PATH': %r, 'HOME': '/h', 'S': 'v'})\n"
        "print(argv[-1])\n"
    ) % _bin(tmp_path, "sudo")
    done = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "TMPDIR": str(tmp_path),
            "PYTHONPATH": str(pathlib.Path(dockerx.__file__).resolve().parents[2]),
        },
        capture_output=True,
        text=True,
        check=True,
    )
    left = pathlib.Path(done.stdout.strip())
    assert left.parent == tmp_path
    assert not left.exists()


def test_neither_route_is_none(tmp_path: pathlib.Path) -> None:
    assert dockerx.group_command("x", user="u", env={"PATH": _bin(tmp_path, "true")}) is None


@pytest.mark.parametrize("with_sg", [True, False])
def test_machine_reexec_routes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, with_sg: bool
) -> None:
    names = ("docker", "sudo", *(("sg",) if with_sg else ()))
    env = {"PATH": _bin(tmp_path, *names), "HOME": "/h", "USER": "alice"}

    class Result:
        def __init__(self, rc: int, out: str) -> None:
            self.rc = rc
            self.out = out

    def run(_self: Ctx, argv: list[str], **_: object) -> Result:
        if argv[:2] == ["docker", "version"]:
            return Result(1, "")
        return Result(0, GROUP if argv[:1] == ["getent"] else "")

    monkeypatch.setattr(Ctx, "run", run)
    monkeypatch.setattr(Ctx, "info", lambda _self, _msg: None)
    monkeypatch.setattr(proc, "exec_replace", _raise_exec)
    monkeypatch.delenv("REDIACC_DOCKER_GROUP_REEXEC", raising=False)
    with pytest.raises(_ExecError) as caught:
        machine.reexec_with_docker_group(tmp_path, ["a"], env)
    argv = caught.value.argv
    assert (argv[0] == "sg") is with_sg
    if not with_sg:
        assert argv[:5] == ["sudo", "-n", "-u", "alice", "env"]
        assert "export REDIACC_DOCKER_GROUP_REEXEC=1" in _env_file(argv).read_text().splitlines()
        assert "run.sh" in argv[-3]
    else:
        assert "run.sh" in argv[-1]


@pytest.mark.parametrize("with_sg", [True, False])
def test_local_common_reexec_routes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, with_sg: bool
) -> None:
    names = ("docker", "sudo", *(("sg",) if with_sg else ()))
    monkeypatch.setenv("PATH", _bin(tmp_path, *names))
    monkeypatch.setenv("HOME", "/h")
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setenv("SCRIPT_ENTRYPOINT", "/x/run.sh")
    monkeypatch.delenv("REDIACC_DOCKER_GROUP_REEXEC", raising=False)
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> int:
        seen.append(list(argv))
        return 1 if argv[:2] == ["docker", "version"] else 0

    monkeypatch.setattr(local_common, "_run", fake_run)
    monkeypatch.setattr(local_common, "_docker_group_members", lambda: "alice")
    monkeypatch.setattr(local_common, "_flush", lambda: None)
    monkeypatch.setattr(proc, "exec_replace", _raise_exec)
    with pytest.raises(_ExecError) as caught:
        local_common.reexec_with_docker_group(["devbox"])
    argv = caught.value.argv
    assert (argv[0] == "sg") is with_sg
    command = -1 if with_sg else -3
    assert any(call[0] == argv[0] and call[command].endswith("docker version") for call in seen)
    if not with_sg:
        assert argv[:5] == ["sudo", "-n", "-u", "alice", "env"]


def test_no_route_returns(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", _bin(tmp_path, "docker"))
    monkeypatch.setenv("USER", "alice")
    monkeypatch.delenv("REDIACC_DOCKER_GROUP_REEXEC", raising=False)
    monkeypatch.setattr(
        local_common, "_run", lambda argv, **_: 1 if argv[:2] == ["docker", "version"] else 0
    )
    monkeypatch.setattr(local_common, "_docker_group_members", lambda: "alice")
    assert local_common.reexec_with_docker_group(["x"]) is True


def test_an_unreadable_environment_file_stops_the_command(tmp_path: pathlib.Path) -> None:
    """Review bf87bfa2.1: when sourcing the file fails the command must not run without its environment; the child exits 126 and the file is gone."""
    marker = tmp_path / "ran"
    env = {"PATH": _bin(tmp_path, "sudo") + os.pathsep + os.environ["PATH"], "HOME": "/h"}
    argv = dockerx.group_command("touch %s" % marker, user="u", env=env, extra_env={"G": "1"})
    assert argv is not None
    child = argv[argv.index("bash") :]
    # Control: with the file readable the same child runs the command.
    ok = subprocess.run(child, env={"PATH": env["PATH"]}, capture_output=True, check=False)
    assert ok.returncode == 0
    assert marker.exists()
    marker.unlink()
    again = dockerx.group_command("touch %s" % marker, user="u", env=env, extra_env={"G": "1"})
    assert again is not None
    carried = _env_file(again)
    carried.unlink()  # the source of a missing file fails
    done = subprocess.run(
        again[again.index("bash") :], env={"PATH": env["PATH"]}, capture_output=True, check=False
    )
    assert done.returncode == 126
    assert not marker.exists()
    assert not carried.exists()


def test_a_root_caller_hands_the_environment_file_to_the_target_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review bf87bfa2.3: a root caller chowns the file to the target user's uid and gid; a non-root caller and an unknown user leave it alone."""
    chowned: list[tuple[str, int, int]] = []

    def chown(path: str, uid: int, gid: int) -> None:
        chowned.append((path, uid, gid))

    entry = types.SimpleNamespace(pw_uid=4242, pw_gid=4343)
    monkeypatch.setattr(os, "chown", chown)
    monkeypatch.setattr(dockerx.pwd, "getpwnam", lambda _user: entry)

    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    plain = dockerx._environment_file({"G": "1"}, "u")
    assert chowned == []

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    rooted = dockerx._environment_file({"G": "1"}, "u")
    assert chowned == [(rooted, 4242, 4343)]

    def missing(_user: str) -> object:
        raise KeyError(_user)

    chowned.clear()
    monkeypatch.setattr(dockerx.pwd, "getpwnam", missing)
    unknown = dockerx._environment_file({"G": "1"}, "nobody-here")
    assert chowned == []
    for path in (plain, rooted, unknown):
        assert pathlib.Path(path).read_text() == "export G=1\n"
