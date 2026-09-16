"""`rediacc_ci.native` against the bash it replaced, and against the sequence it must keep.

WHAT THESE CASES ARE FOR, since `.ci/scripts/quality/check_rdc_native.py` already drives
the nine platform arms end to end in a subprocess. That gate proves the DELEGATION and the
artefact names. These cases go at the parts a subprocess cannot reach cheaply:

  the seam        `plan()` is pure and total: every arm, every uname spelling, and both
                  refusal arms, without spawning an interpreter per row.
  the exe stem    The windows backup name is the one place the bash did string surgery
                  (`${dest%$exe}.old$exe`), and it is the one a naive `dest + ".old"`
                  gets wrong. It gets its own case, in both directions.
  the argv layer  `--system` outside `--print-plan`, an unknown flag, and `--help`. The
                  first is the behaviour change this port MADE and the one most likely to
                  be "helpfully" reverted; the bash ignored trailing arguments in silence.
  no side effects `--print-plan` must not touch the filesystem. A plan that created the
                  install directory would make the "is rdc installed?" refusal
                  unreachable, and that refusal is the only thing stopping a build from
                  landing somewhere nothing on PATH points at.
"""

import json
import os
import pathlib
import subprocess
import sys

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

    The windows arm is the whole case: `rdc.exe` must back up to `rdc.old.exe`, NOT to
    `rdc.exe.old`. cleanupOldBinary() would silently leave the second one on disk forever.
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

    Without this, the gate's mac and win rows could be answered by the host's real Linux
    uname and every one of them would still pass on a Linux box, which is the exact
    vacuity the seam exists to remove.
    """
    monkeypatch.setattr(native._host, "system", lambda: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(native._host, "machine", lambda: (_ for _ in ()).throw(AssertionError()))
    assert native.plan(ROOT, HOME, "Darwin", "arm64").sea_platform == "mac"


def _run(argv, home):
    ci_dir = str(pathlib.Path(native.__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = ci_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["HOME"] = str(home)
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

    `rdc.sh` did `shift` and never looked at `"$@"` again, so `./rdc.sh --native
    --platform win` built for the local platform and said nothing about the flag.
    """
    done = _run(["--platform", "win"], tmp_path)
    assert done.returncode == 2
    assert "--platform" in done.stderr


def test_help_exits_zero_and_names_the_flag(tmp_path):
    done = _run(["--help"], tmp_path)
    assert done.returncode == 0
    assert "--print-plan" in done.stdout
