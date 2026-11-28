"""`rediacc_ci.native` against the bash it replaced, and against the sequence it must keep.

WHAT THESE CASES ARE FOR, since `.ci/scripts/quality/check_rdc_native.py` already drives the nine platform arms end to end in a subprocess. That gate proves the DELEGATION and the artefact names. These cases go at the parts a subprocess cannot reach cheaply:

  the seam        `plan()` is pure and total: every arm, every uname spelling, and both
                  refusal arms, without spawning an interpreter per row.
  the exe stem    The windows backup name is the one place the bash did string surgery
                  (`${dest%$exe}.old$exe`), and it is the one a naive `dest + ".old"`
                  gets wrong. It gets its own case, in both directions.
  the argv layer  `--system` outside `--print-plan`, an unknown flag, and `--help`. The
                  first is the behaviour change this port MADE and the one most likely to
                  be "helpfully" reverted; the bash ignored trailing arguments in silence.
  no side effects `--print-plan` must not touch the filesystem. A plan that created the
                  install directory would be a side effect of a read-only query; the
                  directory is created only by the install step itself.
"""

import json
import os
import pathlib
import subprocess
import sys
import types

import pytest

from rediacc_ci import native

ROOT = "/repo"
HOME = "/home/someone"

# (uname -s, uname -m) -> (sea platform, sea arch, exe). Written out rather than derived,
# for the reason the gate's own table states: a derivation agrees with a broken mapping.
ARMS = {
    ("Linux", "x86_64"): ("linux", "x64", ""),
    ("Linux", "amd64"): ("linux", "x64", ""),
    ("Linux", "aarch64"): ("linux", "arm64", ""),
    ("Linux", "arm64"): ("linux", "arm64", ""),
    ("Darwin", "x86_64"): ("mac", "x64", ""),
    ("Darwin", "arm64"): ("mac", "arm64", ""),
    ("Darwin", "aarch64"): ("mac", "arm64", ""),
    ("MINGW64_NT-10.0-22631", "x86_64"): ("win", "x64", ".exe"),
    ("MSYS_NT-10.0-19045", "amd64"): ("win", "x64", ".exe"),
    ("CYGWIN_NT-10.0", "aarch64"): ("win", "arm64", ".exe"),
}


@pytest.mark.parametrize(("uname", "want"), sorted(ARMS.items()))
def test_plan_matches_the_deleted_bash(uname, want):
    system, machine = uname
    sea_os, sea_arch, exe = want
    got = native.plan(ROOT, HOME, system, machine)
    assert (got.sea_platform, got.sea_arch, got.exe) == (sea_os, sea_arch, exe)
    assert got.built == "%s/dist/cli/rdc-%s-%s%s" % (ROOT, sea_os, sea_arch, exe)
    assert got.dest == "%s/.local/share/rediacc/bin/rdc%s" % (HOME, exe)


def test_the_backup_name_is_what_the_cli_updater_looks_for():
    """`getOldBinaryPath()` in packages/cli/src/utils/platform.ts, and nothing else.

    The windows arm is the whole case: `rdc.exe` must back up to `rdc.old.exe`, NOT to `rdc.exe.old`. cleanupOldBinary() would silently leave the second one on disk forever.
    """
    assert native.plan(ROOT, HOME, "Linux", "x86_64").backup.endswith("/rdc.old")
    assert native.plan(ROOT, HOME, "Darwin", "arm64").backup.endswith("/rdc.old")
    win = native.plan(ROOT, HOME, "MINGW64_NT-10.0", "x86_64")
    assert win.backup.endswith("/rdc.old.exe")
    assert not win.backup.endswith(".exe.old")


@pytest.mark.parametrize(
    ("system", "machine", "fragment"),
    [
        ("Plan9", "x86_64", "Unsupported platform Plan9 for --native"),
        ("SunOS", "x86_64", "Unsupported platform SunOS for --native"),
        ("Linux", "riscv64", "Unsupported arch riscv64 for --native"),
        ("Darwin", "ppc", "Unsupported arch ppc for --native"),
    ],
)
def test_an_unpinned_host_is_refused_by_name(system, machine, fragment):
    """The refusal is the important half: this path overwrites the user's own `rdc`."""
    with pytest.raises(native.NativeError) as exc:
        native.plan(ROOT, HOME, system, machine)
    assert fragment in str(exc.value)


def test_the_seam_is_total_and_the_host_is_never_consulted(monkeypatch):
    """Passing both arguments must not read this machine's uname at all.

    Without this, the gate's mac and win rows could be answered by the host's real Linux uname and every one of them would still pass on a Linux box, which is the exact vacuity the seam exists to remove.
    """
    monkeypatch.setattr(native._host, "system", lambda: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(native._host, "machine", lambda: (_ for _ in ()).throw(AssertionError()))
    assert native.plan(ROOT, HOME, "Darwin", "arm64").sea_platform == "mac"


def _run(argv, home):
    ci_dir = str(pathlib.Path(native.__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = ci_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["HOME"] = str(home)
    # The session resource profiler (.claude/hooks/profile) records every python3 it arms under $HOME/.claude/resprofile; that is the harness, not this program, so it is switched off for the run that asserts the program writes nothing.
    env["WORKLIST_PROFILE"] = "off"
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.native", *argv],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_print_plan_creates_nothing(tmp_path):
    """A plan is an answer, not a step. See the module docstring."""
    home = tmp_path / "home"
    home.mkdir()
    done = _run(["--print-plan", "--system", "Darwin", "--machine", "arm64"], home)
    assert done.returncode == 0, done.stderr
    plan = json.loads(done.stdout)
    assert plan["dest"] == "%s/.local/share/rediacc/bin/rdc" % home
    assert list(home.iterdir()) == []


def test_system_without_print_plan_is_refused(tmp_path):
    """The build installs over the LOCAL rdc, so it cannot be asked to target another."""
    done = _run(["--system", "Darwin"], tmp_path)
    assert done.returncode == 2
    assert "cannot pick what gets BUILT" in done.stderr


def test_an_unknown_argument_is_refused_rather_than_ignored(tmp_path):
    """THE BEHAVIOUR CHANGE THIS PORT MADE, pinned so it is not quietly reverted.

    `rdc.sh` did `shift` and never looked at `"$@"` again, so `./rdc.sh --native --platform win` built for the local platform and said nothing about the flag.
    """
    done = _run(["--platform", "win"], tmp_path)
    assert done.returncode == 2
    assert "--platform" in done.stderr


def test_help_exits_zero_and_names_the_flag(tmp_path):
    done = _run(["--help"], tmp_path)
    assert done.returncode == 0
    assert "--print-plan" in done.stdout


def test_the_sea_child_gets_the_checkout_ci_first_on_pythonpath(monkeypatch, tmp_path):
    """Review finding 4a6641bf.4: the SEA build child imports rediacc_ci by module path, so `<root>/.ci` leads its PYTHONPATH and a caller's entries follow."""
    monkeypatch.setenv("PYTHONPATH", "/caller/site")
    env = native._ci_env(tmp_path)
    assert env["PYTHONPATH"] == "%s%s/caller/site" % (tmp_path / ".ci", os.pathsep)
    monkeypatch.delenv("PYTHONPATH")
    assert native._ci_env(tmp_path)["PYTHONPATH"] == str(tmp_path / ".ci")


def test_the_sea_build_step_runs_from_the_checkout_with_its_ci_env(monkeypatch, tmp_path):
    """Review finding f4a0873d.1: the SEA build call site itself passes cwd=root and the .ci-first env, not only the helper."""
    seen = []

    class StopError(Exception):
        pass

    def fake_stream(argv, cwd=None, env=None):
        seen.append((argv, cwd, env))
        if "rediacc_ci.build.build_cli_executables" in argv:
            raise StopError

    monkeypatch.setattr(native, "_stream", fake_stream)
    monkeypatch.setattr(native, "_renet_account_key", lambda _root: "KEY")
    monkeypatch.setenv("PYTHONPATH", "/caller/site")
    plan = native.plan(tmp_path, tmp_path, "Linux", "x86_64")
    with pytest.raises(StopError):
        native.build_and_install(tmp_path, plan)
    argv, cwd, env = seen[-1]
    assert "rediacc_ci.build.build_cli_executables" in argv
    assert cwd == tmp_path
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(tmp_path / ".ci")


def _install_fixture(monkeypatch, tmp_path):
    """Run build_and_install past the build steps into a tmp install tree; returns (plan, calls, logged steps, dest)."""
    calls = []
    steps: list[str] = []

    def fake_stream(argv, cwd=None, env=None):
        calls.append((argv, cwd, env))

    monkeypatch.setattr(native, "_stream", fake_stream)
    monkeypatch.setattr(native, "_renet_account_key", lambda _root: "KEY123")
    monkeypatch.setattr(native.log, "step", steps.append)
    built = tmp_path / "built" / "rdc"
    built.parent.mkdir()
    built.write_bytes(b"new")
    dest = tmp_path / "share" / "bin" / "rdc"
    plan = native.plan(tmp_path, tmp_path, "Linux", "x86_64")
    plan = native.dataclasses.replace(
        plan, built=str(built), dest=str(dest), backup=str(dest) + ".old"
    )
    return plan, calls, steps, dest


def test_the_stage_linux_call_carries_the_resolved_account_key(monkeypatch, tmp_path):
    plan, calls, _steps, _dest = _install_fixture(monkeypatch, tmp_path)
    native.build_and_install(tmp_path, plan)
    argv, _cwd, env = calls[0]
    assert argv[:2] == ["./build.sh", "stage_linux"]
    assert env["ACCOUNT_ED25519_PUBLIC_KEY"] == "KEY123"


def test_a_missing_install_directory_is_created(monkeypatch, tmp_path):
    plan, _calls, _steps, dest = _install_fixture(monkeypatch, tmp_path)
    assert not dest.parent.exists()
    native.build_and_install(tmp_path, plan)
    assert dest.read_bytes() == b"new"


def test_the_backup_clause_prints_only_when_a_backup_was_written(monkeypatch, tmp_path):
    plan, _calls, steps, dest = _install_fixture(monkeypatch, tmp_path)
    native.build_and_install(tmp_path, plan)
    assert "(backup at" not in steps[-1]
    assert not pathlib.Path(plan.backup).exists()
    dest.write_bytes(b"old")
    steps.clear()
    native.build_and_install(tmp_path, plan)
    assert "backup at %s" % plan.backup in steps[-1]
    assert pathlib.Path(plan.backup).read_bytes() == b"old"


def test_a_missing_renet_licence_key_is_a_native_error_naming_the_exit(monkeypatch, tmp_path):
    """6b050dc6.1: `resolve_renet_account_key` raising LocalCommonError becomes a NativeError that carries its exit code."""

    class LocalCommonError(Exception):
        def __init__(self, code):
            super().__init__(code)
            self.code = code

    def resolve(_dir, _env):
        raise LocalCommonError(7)

    fake = types.SimpleNamespace(
        LocalCommonError=LocalCommonError, resolve_renet_account_key=resolve
    )
    monkeypatch.setattr(native.importlib, "import_module", lambda _name: fake)
    with pytest.raises(native.NativeError, match=r"no renet licence key \(exit 7\)"):
        native._renet_account_key(tmp_path)


def test_an_install_directory_blocked_by_a_file_is_a_native_error(monkeypatch, tmp_path):
    """6b050dc6.2: a regular file where the install directory goes raised FileExistsError as a traceback."""
    plan, _calls, _steps, dest = _install_fixture(monkeypatch, tmp_path)
    dest.parent.parent.mkdir(parents=True)
    dest.parent.write_text("not a directory")
    with pytest.raises(native.NativeError, match="cannot create the install directory"):
        native.build_and_install(tmp_path, plan)
