"""`dockerx.group_command` and the two Python re-exec sites that use it, with `sg` present and absent.

Ubuntu 26.04 ships no `sg` and its sudo is sudo-rs, so the absent route must name `sudo -n -u <user> env PATH= HOME=` explicitly.
"""

import pathlib
import stat

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


def test_sg_present_keeps_sg(tmp_path: pathlib.Path) -> None:
    env = {"PATH": _bin(tmp_path, "sg", "sudo"), "HOME": "/h"}
    assert dockerx.group_command("run it", user="u", env=env) == ["sg", "docker", "-c", "run it"]


def test_sg_absent_uses_sudo_with_path_and_home(tmp_path: pathlib.Path) -> None:
    env = {"PATH": _bin(tmp_path, "sudo"), "HOME": "/h"}
    argv = dockerx.group_command("run it", user="u", env=env, extra_env={"G": "1"})
    assert argv == [
        "sudo",
        "-n",
        "-u",
        "u",
        "env",
        "PATH=%s" % env["PATH"],
        "HOME=/h",
        "G=1",
        "bash",
        "-c",
        "run it",
    ]


def test_sudo_route_keeps_the_rest_of_the_environment_as_sg_does(tmp_path: pathlib.Path) -> None:
    """Review 0ec896a9.1: a token or REDIACC_* setting reaches the re-exec'd run on the sudo route too; an exported function or odd name is not carried."""
    env = {
        "PATH": _bin(tmp_path, "sudo"),
        "HOME": "/h",
        "SCRIPT_ENTRYPOINT": "run.sh",
        "REDIACC_X": "1",
        "BASH_FUNC_f%%": "() { :; }",
        "A-B": "no",
    }
    argv = dockerx.group_command("run it", user="u", env=env, extra_env={"G": "1"})
    assert argv is not None
    carried = argv[argv.index("env") + 1 : argv.index("bash")]
    assert "SCRIPT_ENTRYPOINT=run.sh" in carried
    assert "REDIACC_X=1" in carried
    assert "G=1" in carried
    assert carried.count("PATH=%s" % env["PATH"]) == 1
    assert not any(c.startswith(("BASH_FUNC_", "A-B")) for c in carried)


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
        assert "REDIACC_DOCKER_GROUP_REEXEC=1" in argv
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
    assert any(call[0] == argv[0] and call[-1] == "docker version" for call in seen)
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
