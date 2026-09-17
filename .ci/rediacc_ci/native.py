"""`./rdc.sh --native` -- build the local Node SEA and install it over the user's rdc.

WHAT MOVED AND WHY. This is `rdc.sh:67-159` as it stood on 2026-09-09: ninety-three
lines, sixty of them code, two hand-written `case "$(uname ...)"` blocks and a
seven-step install sequence, sitting in the wrapper a developer types a hundred times
a day to run an ordinary CLI command. Every one of those lines was dead weight on the
common path, and the two case blocks were copies four and five of a mapping this
package already owns: `rediacc_ci.core.platform`'s module docstring cites
`rdc.sh:89` and `rdc.sh:98` BY LINE as two of the fourteen it was written to replace.

THE SEAM, WHICH IS THE POINT OF THE PORT AND NOT A SIDE EFFECT. `plan()` takes
`system` and `machine` as arguments and defaults them to the real `uname`. Nothing
below the argv layer calls `uname` itself. That is what makes the three platform
arms -- linux, mac, win -- checkable from one Linux box: `--print-plan --system
Darwin --machine arm64` answers what the macOS arm WOULD do, and a gate can hold that
answer against the artefact names the deleted bash produced. In bash the same
question needed a Mac, so the mac and win arms of `rdc.sh` were never once executed
by anything in CI.

WHAT IS DELIBERATELY NOT REIMPLEMENTED. `check_node_version`, `ensure_deps` and
`ensure_packages_built` stay in `.ci/lib/local-common.sh` and are reached through one
`bash -c` that sources it. They are shared with `rdc.sh`'s ordinary path, they are
several hundred lines between them, and a second copy here would be the "two
implementations kept in sync" failure the whole transformation exists to remove. One
process, not three, so the sourcing cost is paid once.

TWO BEHAVIOURS CHANGED ON PURPOSE, both stated here rather than discovered later:

  1. TRAILING ARGUMENTS ARE REFUSED. `rdc.sh` did `shift` and then never looked at
     `"$@"` again, so `./rdc.sh --native --platform win` built for the LOCAL platform
     and said nothing. Silence there is a wrong answer, not a convenience.
  2. `Install dir ... does not exist - is rdc installed?` loses its em dash.
     `.ci/rediacc_ci` is a scanned surface for `check:ci-em-dash-surfaces` whose
     baseline refuses additions, and the house rule bans them in authored text.

WHAT IS UNCHANGED, because a port that improves things is a rewrite: the step order,
the artefact paths, the backup naming (`getOldBinaryPath()` in
`packages/cli/src/utils/platform.ts` looks for `rdc.old` / `rdc.old.exe` and will not
find anything else), the refusal on an unsupported platform or arch, the `--version`
run at the end, and the exit codes.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import platform as _host
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `os` appears only in PathLike annotations, never at runtime.
    import os

from rediacc_ci import log
from rediacc_ci.core import platform as plat

# The install root the CLI's own updater uses. Not derived and not configurable: `packages/cli/src/utils/platform.ts` hard-codes the same path, and a second spelling here would install somewhere the CLI does not look.
INSTALL_SUBDIR = (".local", "share", "rediacc", "bin")

# `dist/cli/rdc-<platform>-<arch><exe>`, which is where `.ci/scripts/build/build-cli-executables.sh` writes and nowhere else.
BUILD_SUBDIR = ("dist", "cli")

USAGE = """usage: python3 -m rediacc_ci.native [--print-plan [--system S] [--machine M]]

Reached as `./rdc.sh --native`. With no arguments it builds the SEA for this host
and installs it over ~/.local/share/rediacc/bin/rdc.

  --print-plan      print the plan as JSON and do nothing else
  --system  <s>     a `uname -s` value; only with --print-plan
  --machine <m>     a `uname -m` value; only with --print-plan
"""


class NativeError(RuntimeError):
    """A refusal with a message a person can act on. Never a stack trace."""


@dataclasses.dataclass(frozen=True)
class Plan:
    """Every path and name the build/install sequence needs, and no side effects.

    Frozen and pure so a gate can compare three of these against a table without
    a Mac, a Windows box, or a build. `sea_platform` and `sea_arch` are the exact
    strings `build-cli-executables.sh` takes for `--platform` and `--arch`.
    """

    sea_platform: str
    sea_arch: str
    exe: str
    built: str
    dest: str
    backup: str

    def as_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


def plan(
    root: str | os.PathLike[str],
    home: str | os.PathLike[str],
    system: str | None = None,
    machine: str | None = None,
) -> Plan:
    """The whole uname-dependent half of `./rdc.sh --native`, as data.

    `system` and `machine` default to this host's uname. Passing them is the seam:
    the mac and win arms are then reachable from a Linux gate.

    Raises NativeError, not the package's UnsupportedPlatformError, so the caller
    has one exception type to print and the message keeps the wording the bash
    refusal had ("Unsupported platform X for --native").
    """
    # The raw uname strings, resolved HERE and passed down explicitly. `os_for` and `arch_for` would default to the host themselves, but then the refusal below could not name what it refused, and the bash it replaces printed the raw value: "Unsupported platform MINGW32_NT-6.1 for --native" is actionable, "None" is not.
    real_system = system if system is not None else _host.system()
    real_machine = machine if machine is not None else _host.machine()
    try:
        sea_platform = plat.os_for("sea", real_system)
        exe = plat.exe_suffix(real_system)
    except plat.UnsupportedPlatformError:
        raise NativeError("Unsupported platform %s for --native" % real_system) from None
    try:
        sea_arch = plat.arch_for("node", real_machine)
    except plat.UnsupportedPlatformError:
        raise NativeError("Unsupported arch %s for --native" % real_machine) from None

    root_path = pathlib.Path(root)
    home_path = pathlib.Path(home)
    built = root_path.joinpath(*BUILD_SUBDIR, "rdc-%s-%s%s" % (sea_platform, sea_arch, exe))
    dest = home_path.joinpath(*INSTALL_SUBDIR, "rdc%s" % exe)
    # `${dest%$exe}.old$exe` in bash: rdc.old on Linux and macOS, rdc.old.exe on
    # Windows. cleanupOldBinary() in packages/cli/src/utils/platform.ts looks for exactly this and silently leaves anything else behind.
    stem = str(dest)[: len(str(dest)) - len(exe)] if exe else str(dest)
    return Plan(
        sea_platform=sea_platform,
        sea_arch=sea_arch,
        exe=exe,
        built=str(built),
        dest=str(dest),
        backup="%s.old%s" % (stem, exe),
    )


def _stream(argv: list[str], cwd: str | os.PathLike[str] | None = None) -> None:
    """Run a build step with the terminal attached, and raise on failure.

    NOT `rediacc_ci.proc.run`, and the reason is not style. `proc.run` captures both
    streams and bounds the command at 60 seconds; a two-arch Go cross-compile plus an
    esbuild bundle plus a SEA injection is minutes of output a person watches to know
    it is alive. Swallowing that and killing it at 60 seconds would both be wrong.
    """
    completed = subprocess.run(argv, cwd=None if cwd is None else str(cwd), check=False)
    if completed.returncode != 0:
        raise NativeError("%s exited %d" % (argv[0], completed.returncode))


# The bash the three shared helpers are reached through, as ONE program. Written out here rather than inline so the call below reads as a call, and so the exact sequence a reviewer has to compare against `rdc.sh`'s old lines 143-145 is on consecutive lines.
_PREPARE_PROGRAM = """
set -euo pipefail
source "$1/.ci/config/constants.sh"
source "$1/.ci/lib/local-common.sh"
check_node_version "$NODE_VERSION_MIN"
ensure_deps
ensure_packages_built
"""


def prepare_toolchain(root: pathlib.Path) -> None:
    """node version + deps + built packages, through the bash that already owns them.

    ONE bash, not three: sourcing `local-common.sh` is the expensive part and the
    three calls are one logical step. `set -euo pipefail` inside, so the first
    failure is the exit code, exactly as it was when these three lines sat in
    `rdc.sh` under its own `set -e`.

    THE ORDER IS THE BASH ORDER. `check_node_version` first: `ensure_deps` runs npm,
    and npm on an unsupported node produces a worse message than the version check.
    """
    _stream(
        [
            "bash",
            "-c",
            _PREPARE_PROGRAM,
            "rediacc_ci.native",
            str(root),
        ]
    )


def build_and_install(root: pathlib.Path, built_plan: Plan) -> None:
    """Steps 1-3 of the sequence `rdc.sh`'s header documented, in that order."""
    # 1. Cross-build renet for BOTH linux arches into the slots build-cli-executables.sh embeds (private/bin/renet-linux-<arch>). The SEA embeds linux renet binaries for remote provisioning and a remote machine may be amd64 or arm64, so both must be present. Delegated to build.sh's stage_linux so the per-arch cross-compile lives in exactly one place.
    log.step("Cross-building renet (both linux arches) -> private/bin")
    _stream(
        ["./build.sh", "stage_linux", str(root / "private" / "bin")], cwd=root / "private" / "renet"
    )

    # 2. Assemble the SEA. sea-inject/ streams the blob and has no size ceiling.
    log.step("Building SEA for %s/%s" % (built_plan.sea_platform, built_plan.sea_arch))
    _stream(
        [
            "bash",
            str(root / ".ci" / "scripts" / "build" / "build-cli-executables.sh"),
            "--platform",
            built_plan.sea_platform,
            "--arch",
            built_plan.sea_arch,
        ]
    )
    if not pathlib.Path(built_plan.built).is_file():
        raise NativeError("Built SEA not found at %s" % built_plan.built)

    # 3. Back up the existing user binary and replace it. The install directory is NOT created: its absence means rdc was never installed, and silently creating it would put a binary somewhere nothing on PATH points at.
    dest = pathlib.Path(built_plan.dest)
    if not dest.parent.is_dir():
        raise NativeError("Install dir %s does not exist; is rdc installed?" % dest.parent)
    if dest.is_file():
        _copy(dest, pathlib.Path(built_plan.backup))
    _copy(pathlib.Path(built_plan.built), dest)
    dest.chmod(0o755)
    log.step("Installed dev SEA -> %s (backup at %s)" % (dest, built_plan.backup))
    _stream([str(dest), "--version"])


def _copy(src: pathlib.Path, dst: pathlib.Path) -> None:
    """`cp -f`: overwrite the CONTENT, never replace the inode.

    shutil.copyfile, not shutil.copy2 and not a rename. `~/.local/bin/rdc` is a
    SYMLINK to the destination in every documented setup, and a rename would leave
    that link dangling while a metadata copy would carry the build tree's mtime onto
    a binary the updater compares by version string.
    """
    dst.write_bytes(src.read_bytes())


def main(argv: list[str]) -> int:
    print_plan = False
    system: str | None = None
    machine: str | None = None
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--print-plan":
            print_plan = True
        elif arg == "--system" and rest:
            system = rest.pop(0)
        elif arg == "--machine" and rest:
            machine = rest.pop(0)
        elif arg in ("-h", "--help"):
            print(USAGE)
            return 0
        else:
            # THE BASH IGNORED THIS SILENTLY. See the module docstring.
            log.error("unknown argument %r" % arg)
            print(USAGE, file=sys.stderr)
            return 2
    if (system is not None or machine is not None) and not print_plan:
        log.error("--system / --machine describe a plan; they cannot pick what gets BUILT")
        log.error("this path installs over the local rdc, so it builds for this host only")
        return 2

    root = pathlib.Path(__file__).resolve().parents[2]
    try:
        built_plan = plan(root, pathlib.Path.home(), system, machine)
    except NativeError as exc:
        log.error(str(exc))
        return 1

    if print_plan:
        print(json.dumps(built_plan.as_dict(), indent=2, sort_keys=True))
        return 0

    try:
        prepare_toolchain(root)
        build_and_install(root, built_plan)
    except NativeError as exc:
        log.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
