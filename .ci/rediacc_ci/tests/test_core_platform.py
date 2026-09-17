"""`rediacc_ci.core.platform` against the fourteen bash `case` blocks it unifies.

WHAT EACH GROUP OF CASES GUARDS.

  the OS map      `os_name()` against the frozen `_toolchain_os`
                  (.ci/scripts/lib/toolchain.sh:303), driven with a stubbed
                  `uname` so both arms AND the refusal arm are exercised on any
                  host. A test that only ever ran on Linux would prove one third
                  of the function.
  the three arch  Three upstreams spell the same two architectures three ways,
  spellings       and each row of `ARCH_NAMES` is compared against the frozen
                  `case` that builds that upstream's URL. Plus the PAIRWISE
                  assertion that no row is redundant, which is what stops someone
                  collapsing the table into one "normalized arch" and handing
                  `x86_64` to a shfmt URL that needs `amd64`.
  uv_target       Compared field for field against `uv_target` at
                  `.ci/bootstrap.sh:91`, over the whole OS x machine cross
                  product, because the checksum key it returns is what decides
                  whether a download is verified against the right hash.
  WSL             Fixture kernels planted under a tmpdir, so the detector is
                  asserted in BOTH directions and the SIGNAL IT NAMES is checked,
                  on a host that may be either. Plus a differential against the
                  live `grep -qi microsoft /proc/version` at
                  `.ci/lib/setup.sh:588`, which is what this host really is.
  sha256          A PATH with only `sha256sum`, a PATH with only `shasum`, and a
                  PATH with neither. The third is the case the whole helper
                  exists for and it must RAISE.
  Windows         Never native, and the refusal must name launchers that exist
                  and that really re-enter WSL.

THE DEFECT THE MODULE IS SHAPED BY, and the state of it as measured today. `toolchain.sh` used to hardcode the literal `linux` into both download URLs while deriving only the arch from `uname -m`, so an arm64 Mac downloaded a Linux binary, VERIFIED it against the ARM64 checksum, chmod +x'd it, and failed much later with "cannot execute binary file". Its sibling was a bare
`sha256sum`, which does not exist on macOS and whose absence surfaced as a checksum MISMATCH that never happened. Both are FIXED in the live file (`_toolchain_os` at :303, `_toolchain_sha256sum` at :282), so the cases at the bottom of this file pin the fix rather than reproduce the bug -- with a control proving each pattern would still catch a regression.
"""

import hashlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import platform as plat
from rediacc_ci.tests import differential as diff

TOOLCHAIN_SH = ".ci/scripts/lib/toolchain.sh"
SETUP_SH = ".ci/lib/setup.sh"
RUN_PS1 = "run.ps1"

# The `uname -s` strings a host really presents, and the ones this repo's own `case` blocks already list. MINGW/MSYS/CYGWIN are not hypothetical: both `.ci/lib/local-common.sh:795` and `rdc.sh:98` branch on them for a `.exe`. WHAT `uname -s` REALLY PRINTS. There is no `Windows` here, and its absence is the point: on Windows the only shells that HAVE uname are Git Bash, MSYS2 and
# Cygwin, and each prints its own `<flavour>_NT-<build>` string. So this is the corpus every bash differential is driven with, and a `Windows` in it would ask the frozen `case` about an input it can never receive.
UNAME_SYSTEMS = ("Linux", "Darwin", "MINGW64_NT-10.0-22631", "MSYS_NT-10.0", "CYGWIN_NT-10.0")

# WHAT THE PYTHON MODULE MUST HANDLE, which is a strict superset. A native
# Windows CPython answers `platform.system() == "Windows"` and never goes near
# uname, so `os_name()` has to map that string too -- and the two corpora are separate because the first draft used one for both and the differential failed on `Windows` for a reason that was the TEST's, not the module's.
SYSTEMS = (*UNAME_SYSTEMS, "Windows")
UNSUPPORTED_SYSTEMS = ("SunOS", "FreeBSD", "AIX", "")

# The `uname -m` strings, both spellings of each architecture, exactly the pairs every `case` in the tree accepts.
MACHINES = ("x86_64", "amd64", "aarch64", "arm64")
UNSUPPORTED_MACHINES = ("ppc64le", "i686", "riscv64", "armv7l", "")

# A stub `uname`. A shell FUNCTION rather than a script on PATH, because the frozen bodies call it inside `$(...)` and command-substitution subshells inherit functions -- which keeps the fixture to one string with no tempdir.
FAKE_UNAME = """
uname() {
    case "$1" in
        -s) printf '%s\\n' "$FAKE_S" ;;
        -m) printf '%s\\n' "$FAKE_M" ;;
        *) return 1 ;;
    esac
}
"""

# --- the frozen bash, each block copied from the file that builds its URL -----

# .ci/scripts/lib/toolchain.sh:303-312
FROZEN_OS = """
_toolchain_os() {
    case "$(uname -s)" in
        Linux) printf 'linux' ;;
        Darwin) printf 'darwin' ;;
        *)
            echo "toolchain: unsupported OS '$(uname -s)'" >&2
            return 1
            ;;
    esac
}
"""

# .ci/scripts/lib/toolchain.sh:319-326 -- the shfmt asset, Go's GOARCH naming.
FROZEN_ARCH_GOARCH = """
frozen_arch() {
    local arch
    case "$(uname -m)" in
        x86_64 | amd64) arch=amd64 ;;
        aarch64 | arm64) arch=arm64 ;;
        *) return 1 ;;
    esac
    printf '%s' "$arch"
}
"""

# .ci/scripts/lib/toolchain.sh:393-400 -- the shellcheck asset, raw uname naming.
FROZEN_ARCH_UNAME = """
frozen_arch() {
    local arch
    case "$(uname -m)" in
        x86_64 | amd64) arch=x86_64 ;;
        aarch64 | arm64) arch=aarch64 ;;
        *) return 1 ;;
    esac
    printf '%s' "$arch"
}
"""

# .ci/lib/setup.sh:105-111 -- the Node tarball, Node's own naming.
FROZEN_ARCH_NODE = """
frozen_arch() {
    local arch
    case "$(uname -m)" in
        x86_64 | amd64) arch=x64 ;;
        aarch64 | arm64) arch=arm64 ;;
        *) return 1 ;;
    esac
    printf '%s' "$arch"
}
"""

# .ci/bootstrap.sh:91-116, minus the trailing-newline commentary.
FROZEN_UV_TARGET = """
uv_target() {
    local os arch triple sfx
    case "$(uname -s)" in
        Linux) os=unknown-linux-gnu sfx=LINUX ;;
        Darwin) os=apple-darwin sfx=DARWIN ;;
        *) return 1 ;;
    esac
    case "$(uname -m)" in
        x86_64 | amd64) arch=x86_64 sfx="${sfx}_X86_64" ;;
        aarch64 | arm64) arch=aarch64 sfx="${sfx}_AARCH64" ;;
        *) return 1 ;;
    esac
    triple="${arch}-${os}"
    printf '%s %s\\n' "$triple" "$sfx"
}
"""


# .ci/scripts/build/build-cli-executables.sh:61-69, whose arms rdc.sh:89-106 repeats verbatim for the same artefact names.
FROZEN_OS_SEA = """
frozen_os_sea() {
    case "$(uname -s)" in
        Linux*) printf 'linux' ;;
        Darwin*) printf 'mac' ;;
        MINGW* | MSYS* | CYGWIN*) printf 'win' ;;
        *) return 1 ;;
    esac
}
"""

# The `.exe` half of the same decision: .ci/lib/local-common.sh:794-796 and .ci/scripts/infra/build-renet.sh:32-34, which are two copies of one fact.
FROZEN_EXE = """
frozen_exe() {
    local ext=""
    case "$(uname -s)" in
        MINGW* | MSYS* | CYGWIN*) ext=".exe" ;;
    esac
    printf '%s' "$ext"
}
"""

FROZEN_ARCH = {
    "goarch": FROZEN_ARCH_GOARCH,
    "uname": FROZEN_ARCH_UNAME,
    "node": FROZEN_ARCH_NODE,
}


def _bash(script: str, system: str = "Linux", machine: str = "x86_64"):
    return diff.bash_streams(
        FAKE_UNAME + script,
        env=diff.env_for(FAKE_S=system, FAKE_M=machine),
    )


# --------------------------------------------------------------------------- the OS map ---------------------------------------------------------------------------


@pytest.mark.parametrize("system", ["Linux", "Darwin"])
def test_os_name_matches_the_frozen_toolchain_os(system: str) -> None:
    rc, out, err = _bash(FROZEN_OS + "\n_toolchain_os\n", system=system)
    assert rc == 0, err
    assert out == plat.os_name(system)


@pytest.mark.parametrize("system", UNSUPPORTED_SYSTEMS)
def test_unsupported_os_refuses_and_the_bash_agrees(system: str) -> None:
    """BOTH DIRECTIONS. Falling through to a default is how a Linux binary got
    installed on a Mac and passed its checksum."""
    rc, out, _ = _bash(FROZEN_OS + "\n_toolchain_os\n", system=system)
    assert rc == 1
    assert out == ""
    with pytest.raises(plat.UnsupportedPlatformError):
        plat.os_name(system)


@pytest.mark.parametrize("system", SYSTEMS)
def test_every_supported_system_string_maps(system: str) -> None:
    """CONTROL for the refusal above: a function that raised on everything would
    pass every unsupported case and this is what catches it."""
    assert plat.os_name(system) in (plat.OS_LINUX, plat.OS_DARWIN, plat.OS_WINDOWS)


def test_the_uname_corpus_carries_no_bare_windows() -> None:
    """CONTROL for the corpus split, so the two lists cannot silently merge.

    `uname -s` cannot print `Windows`; only a native CPython says that. If the
    two corpora are ever unified, the frozen `case` differentials would be asked about an input no shell produces and would fail for the test's reason rather than the module's -- which is exactly how they DID fail once.
    """
    assert "Windows" not in UNAME_SYSTEMS
    assert "Windows" in SYSTEMS
    assert set(UNAME_SYSTEMS) < set(SYSTEMS)


def test_windows_shells_all_land_on_windows() -> None:
    """Git Bash, MSYS2 and Cygwin are one answer, matched by PREFIX.

    The real strings carry a version (`MINGW64_NT-10.0-22631`), so an equality test against `MINGW64` would have silently failed on a newer build of the same shell.
    """
    seen = {plat.os_name(s) for s in SYSTEMS if s not in ("Linux", "Darwin")}
    assert seen == {plat.OS_WINDOWS}


def test_wsl_reports_as_linux_not_as_a_fourth_os() -> None:
    """Every artefact WSL downloads is the Linux one, so the OS answer is linux.

    Driven from the real host: whatever this machine is, `os_name()` and the WSL question must be independent of each other.
    """
    assert plat.os_name("Linux") == plat.OS_LINUX
    assert plat.detect_wsl().is_wsl in (True, False)


# --------------------------------------------------------------------------- the three arch spellings ---------------------------------------------------------------------------


@pytest.mark.parametrize("machine", MACHINES)
@pytest.mark.parametrize("scheme", sorted(FROZEN_ARCH))
def test_arch_for_matches_the_frozen_case_that_builds_that_url(scheme: str, machine: str) -> None:
    rc, out, err = _bash(FROZEN_ARCH[scheme] + "\nfrozen_arch\n", machine=machine)
    assert rc == 0, err
    assert out == plat.arch_for(scheme, machine)


def test_every_scheme_in_the_table_has_a_frozen_twin() -> None:
    """The table and the differential cover the same set, or a row is untested."""
    assert set(plat.ARCH_NAMES) == set(FROZEN_ARCH)


@pytest.mark.parametrize("machine", UNSUPPORTED_MACHINES)
def test_unsupported_machine_refuses_and_the_bash_agrees(machine: str) -> None:
    rc, out, _ = _bash(FROZEN_ARCH_GOARCH + "\nfrozen_arch\n", machine=machine)
    assert rc == 1
    assert out == ""
    with pytest.raises(plat.UnsupportedPlatformError):
        plat.machine_key(machine)


@pytest.mark.parametrize("machine", MACHINES)
def test_machine_key_folds_both_spellings(machine: str) -> None:
    """CONTROL for the refusal: the supported set must actually resolve."""
    assert plat.machine_key(machine) in ("x86_64", "aarch64")


def test_no_two_schemes_are_redundant() -> None:
    """A single "normalized arch" would be wrong for two of the three upstreams.

    Stated PAIRWISE and not as "all three answers differ", which is what the first draft asserted and which is false: `goarch` and `node` both spell aarch64 as `arm64` and diverge only on x86_64 (`amd64` vs `x64`). The real property is that no row can be deleted -- every pair of schemes disagrees somewhere -- and that is what makes collapsing the table a behaviour change rather
    than a tidy-up.
    """
    keys = sorted(plat.MACHINE_ALIASES.values())
    schemes = sorted(plat.ARCH_NAMES)
    for i, left in enumerate(schemes):
        for right in schemes[i + 1 :]:
            differ = [k for k in keys if plat.arch_for(left, k) != plat.arch_for(right, k)]
            assert differ, "%s and %s answer identically everywhere" % (left, right)


@pytest.mark.parametrize("system", UNAME_SYSTEMS)
def test_os_for_sea_matches_the_frozen_artefact_naming(system: str) -> None:
    """`linux | mac | win` is a SECOND OS spelling and it is not derivable.

    No rule turns `darwin` into `mac`, so the table carries both and this compares the `sea` row against the case block that names the executables.
    """
    rc, out, err = _bash(FROZEN_OS_SEA + "\nfrozen_os_sea\n", system=system)
    assert rc == 0, err
    assert out == plat.os_for("sea", system)


@pytest.mark.parametrize("system", UNAME_SYSTEMS)
def test_exe_suffix_matches_the_frozen_case(system: str) -> None:
    rc, out, err = _bash(FROZEN_EXE + "\nfrozen_exe\n", system=system)
    assert rc == 0, err
    assert out == plat.exe_suffix(system)


def test_the_two_os_spellings_are_not_redundant() -> None:
    """PLANTED DEFECT for the case above: `asset` and `sea` must disagree.

    If they ever answer identically everywhere, one of the two rows was written
    from the other and the differential proves nothing.
    """
    differ = [s for s in SYSTEMS if plat.os_for("asset", s) != plat.os_for("sea", s)]
    assert differ, "the asset and sea spellings collapsed"


def test_os_for_refuses_an_unknown_scheme() -> None:
    with pytest.raises(plat.UnsupportedPlatformError, match="unknown OS scheme"):
        plat.os_for("posix", "Linux")


def test_os_for_control_a_known_scheme_answers() -> None:
    assert plat.os_for("asset", "Darwin") == plat.OS_DARWIN
    assert plat.os_for("sea", "Darwin") == "mac"


def test_exe_suffix_is_empty_off_windows_and_set_on_it() -> None:
    """CONTROL in both directions on the same function."""
    assert plat.exe_suffix("Linux") == ""
    assert plat.exe_suffix("Darwin") == ""
    assert plat.exe_suffix("MINGW64_NT-10.0-22631") == ".exe"


def test_the_arch_differential_can_fail() -> None:
    """THE PLANTED DEFECT for the differential above.

    Feed the frozen shfmt `case` the answer from the WRONG scheme and it must disagree. Without this, `test_arch_for_matches_the_frozen_case...` proves only that two things agree, not that the comparison can tell them apart -- and a table that had collapsed to one spelling would sail through it.
    """
    rc, out, err = _bash(FROZEN_ARCH_GOARCH + "\nfrozen_arch\n", machine="x86_64")
    assert rc == 0, err
    assert out == plat.arch_for("goarch", "x86_64")
    assert out != plat.arch_for("uname", "x86_64")
    assert out != plat.arch_for("node", "x86_64")


def test_the_os_differential_can_fail() -> None:
    """The same, for the literal `linux` the original defect hardcoded.

    `_toolchain_os` on a Mac must answer something OTHER than `linux`, or the differential would pass against the very bug it exists to keep out.
    """
    rc, out, err = _bash(FROZEN_OS + "\n_toolchain_os\n", system="Darwin")
    assert rc == 0, err
    assert out == plat.os_name("Darwin")
    assert out != plat.os_name("Linux")


def test_the_uv_target_differential_can_fail() -> None:
    """And for uv, where the second field selects the checksum to verify against."""
    rc, out, err = _bash(FROZEN_UV_TARGET + "\nuv_target\n", system="Darwin", machine="arm64")
    assert rc == 0, err
    assert out.split() == list(plat.uv_target("Darwin", "arm64"))
    assert out.split() != list(plat.uv_target("Linux", "arm64"))
    assert out.split() != list(plat.uv_target("Darwin", "x86_64"))


def test_arch_for_refuses_an_unknown_scheme() -> None:
    with pytest.raises(plat.UnsupportedPlatformError, match="unknown arch scheme"):
        plat.arch_for("gnu-triplet", "x86_64")


def test_arch_for_control_a_known_scheme_answers() -> None:
    assert plat.arch_for("goarch", "x86_64") == "amd64"


# --------------------------------------------------------------------------- uv_target ---------------------------------------------------------------------------


@pytest.mark.parametrize("machine", MACHINES)
@pytest.mark.parametrize("system", ["Linux", "Darwin"])
def test_uv_target_matches_the_frozen_bootstrap(system: str, machine: str) -> None:
    """Both fields, over the whole cross product.

    The second field completes `UV_SHA256_<suffix>`, so a divergence here is a download verified against another platform's hash, which is worse than a 404.
    """
    rc, out, err = _bash(FROZEN_UV_TARGET + "\nuv_target\n", system=system, machine=machine)
    assert rc == 0, err
    assert out.split() == list(plat.uv_target(system, machine))


@pytest.mark.parametrize("machine", MACHINES)
@pytest.mark.parametrize("system", ["Linux", "Darwin"])
def test_uv_checksum_key_is_a_key_the_pins_file_defines(system: str, machine: str) -> None:
    """All four are recorded, not just this host's, which is the point of the fix.

    Read from the live pins file rather than listed here, so a checksum removed
    from that file stops this passing the same day.
    """
    from rediacc_ci.core import toolchain  # noqa: PLC0415 -- one case needs the pins

    pins = toolchain.load_pins()
    key = plat.uv_checksum_key(system, machine)
    assert key in pins, "%s is missing from %s" % (key, toolchain.pins_file())
    assert pins[key].strip()


def test_uv_target_refuses_windows() -> None:
    """uv publishes Windows builds; this repo records no checksum for one, and a
    download nobody recorded a hash for must be refused rather than trusted."""
    with pytest.raises(plat.UnsupportedPlatformError):
        plat.uv_target("MINGW64_NT-10.0-22631", "x86_64")


# --------------------------------------------------------------------------- WSL: evidence, in both directions, with the signal named ---------------------------------------------------------------------------

# Real banners. `/proc/version` here is the string a WSL2 kernel prints, and the
# Debian one is a real non-WSL banner; neither is a shortened stand-in, because a
# substring match is what is being tested.
WSL_VERSION_BANNER = (
    "Linux version 5.15.167.4-microsoft-standard-WSL2 "
    "(root@f9c826d3017f) (gcc (GCC) 11.2.0, GNU ld (GNU Binutils) 2.37) "
    "#1 SMP Tue Nov 5 00:21:55 UTC 2024\n"
)
PLAIN_VERSION_BANNER = (
    "Linux version 6.1.0-28-amd64 (debian-kernel@lists.debian.org) "
    "(gcc-12 (Debian 12.2.0-14) 12.2.0, GNU ld (GNU Binutils for Debian) 2.40) "
    "#1 SMP PREEMPT_DYNAMIC Debian 6.1.119-1 (2024-11-22)\n"
)
WSL_OSRELEASE = "5.15.167.4-microsoft-standard-WSL2\n"
PLAIN_OSRELEASE = "6.1.0-28-amd64\n"


def _plant(tmp_path, version: str | None, osrelease: str | None):
    """Build a fake `/` carrying the two files `detect_wsl` reads.

    A `None` means the file is ABSENT, which is the macOS case and a different thing from a file whose contents do not match.
    """
    root = tmp_path / "fakeroot"
    (root / "proc" / "sys" / "kernel").mkdir(parents=True)
    if version is not None:
        (root / "proc" / "version").write_text(version, encoding="utf-8")
    if osrelease is not None:
        (root / "proc" / "sys" / "kernel" / "osrelease").write_text(osrelease, encoding="utf-8")
    return root


def test_the_wsl_fixtures_are_actually_discriminating() -> None:
    """THE PLANTED DEFECT for the WSL cases: the fixtures must not all match.

    Asserted against the marker list itself rather than by eye. If someone "fixes" PLAIN_VERSION_BANNER to a string that happens to contain `wsl`, or widens WSL_MARKERS to something every kernel carries, every case below would pass while detecting nothing.
    """
    lowered = {
        "wsl-version": WSL_VERSION_BANNER.lower(),
        "wsl-osrelease": WSL_OSRELEASE.lower(),
    }
    plain = {
        "plain-version": PLAIN_VERSION_BANNER.lower(),
        "plain-osrelease": PLAIN_OSRELEASE.lower(),
    }
    for name, text in lowered.items():
        assert any(marker in text for marker in plat.WSL_MARKERS), name
    for name, text in plain.items():
        assert not any(marker in text for marker in plat.WSL_MARKERS), name


def test_wsl_is_detected_from_proc_version(tmp_path) -> None:
    root = _plant(tmp_path, WSL_VERSION_BANNER, PLAIN_OSRELEASE)
    evidence = plat.detect_wsl(root, env={})
    assert evidence.is_wsl is True
    assert [source for source, _ in evidence.signals] == ["proc/version"]
    assert "proc/version" in evidence.describe()


def test_wsl_is_detected_from_osrelease_alone(tmp_path) -> None:
    """The kernel whose banner does NOT say Microsoft but whose release does.

    Reading only /proc/version would answer "not WSL" here, which is why two files are read and why the detector reports which one fired.
    """
    root = _plant(tmp_path, PLAIN_VERSION_BANNER, WSL_OSRELEASE)
    evidence = plat.detect_wsl(root, env={})
    assert evidence.is_wsl is True
    assert [source for source, _ in evidence.signals] == ["proc/sys/kernel/osrelease"]


def test_both_signals_are_reported_when_both_fire(tmp_path) -> None:
    root = _plant(tmp_path, WSL_VERSION_BANNER, WSL_OSRELEASE)
    evidence = plat.detect_wsl(root, env={})
    assert {source for source, _ in evidence.signals} == set(plat.WSL_PROC_FILES)


def test_a_plain_linux_kernel_is_not_wsl(tmp_path) -> None:
    """THE CONTROL. Without it, a detector that returned True unconditionally
    passes all three cases above."""
    root = _plant(tmp_path, PLAIN_VERSION_BANNER, PLAIN_OSRELEASE)
    evidence = plat.detect_wsl(root, env={})
    assert evidence.is_wsl is False
    assert evidence.signals == ()
    assert "not WSL" in evidence.describe()


def test_absent_proc_is_not_wsl_and_does_not_raise(tmp_path) -> None:
    """macOS has no /proc at all, and `detect_wsl()` must answer there."""
    root = _plant(tmp_path, None, None)
    assert plat.detect_wsl(root, env={}).is_wsl is False


def test_an_environment_variable_alone_is_not_evidence(tmp_path) -> None:
    """The anti-guess assertion, and the reason this is not `if WSL_DISTRO_NAME`.

    That variable is inherited by everything the shell spawns: it survives an `ssh` from a WSL host into a plain Linux VM, and `wsl.exe -- env` carries it the other way. So it is RECORDED, and the verdict is /proc's alone.
    """
    root = _plant(tmp_path, PLAIN_VERSION_BANNER, PLAIN_OSRELEASE)
    evidence = plat.detect_wsl(root, env={"WSL_DISTRO_NAME": "Ubuntu", "WSL_INTEROP": "/run/x"})
    assert evidence.is_wsl is False
    assert evidence.distro == "Ubuntu"
    assert set(evidence.env_signals) == {"WSL_DISTRO_NAME", "WSL_INTEROP"}


def test_env_signals_control_they_are_empty_when_unset(tmp_path) -> None:
    """CONTROL for the case above: `env_signals` must be capable of being empty,
    or "recorded but not decisive" would be indistinguishable from "ignored"."""
    root = _plant(tmp_path, WSL_VERSION_BANNER, WSL_OSRELEASE)
    evidence = plat.detect_wsl(root, env={})
    assert evidence.env_signals == ()
    assert evidence.is_wsl is True


def test_detection_agrees_with_the_live_bash_on_this_host() -> None:
    """The differential against what `.ci/lib/setup.sh:588` really asks.

    Host-independent by construction: it asserts AGREEMENT, not WSL-ness, so it is a real case on a WSL machine, on a plain Linux runner and on a Mac.
    """
    rc, _, _ = diff.bash_streams("grep -qi microsoft /proc/version 2>/dev/null", env=diff.env_for())
    fired = ("proc/version", "microsoft") in plat.detect_wsl().signals
    assert fired is (rc == 0)


# --------------------------------------------------------------------------- sha256: the macOS half of the same defect ---------------------------------------------------------------------------


def _stub_path(tmp_path, *names: str) -> str:
    """A directory holding executable stubs, returned as a PATH value."""
    bindir = tmp_path / ("bin-" + "-".join(names or ("empty",)))
    bindir.mkdir()
    for name in names:
        stub = bindir / name
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    return str(bindir)


def test_sha256_command_prefers_the_gnu_name(tmp_path) -> None:
    env = {"PATH": _stub_path(tmp_path, "sha256sum", "shasum")}
    assert plat.sha256_command(env=env) == ["sha256sum"]


def test_sha256_command_falls_back_to_shasum(tmp_path) -> None:
    """The macOS PATH: no `sha256sum`, and `shasum` needs its `-a 256`."""
    env = {"PATH": _stub_path(tmp_path, "shasum")}
    assert plat.sha256_command(env=env) == ["shasum", "-a", "256"]


def test_sha256_command_raises_when_there_is_neither(tmp_path) -> None:
    """THE CASE THE HELPER EXISTS FOR. Returning ["sha256sum"] and hoping is what
    turned "cannot verify" into a checksum MISMATCH that never happened."""
    env = {"PATH": _stub_path(tmp_path)}
    with pytest.raises(plat.MissingToolError, match="no sha256 tool"):
        plat.sha256_command(env=env)


def test_missing_tool_is_not_an_unsupported_platform(tmp_path) -> None:
    """macOS is a SUPPORTED platform that is missing one binary, and conflating
    the two is how the original message misled."""
    env = {"PATH": _stub_path(tmp_path)}
    with pytest.raises(plat.MissingToolError):
        plat.sha256_command(env=env)
    assert not issubclass(plat.MissingToolError, plat.UnsupportedPlatformError)


def test_the_returned_argv_actually_computes_the_right_digest(tmp_path) -> None:
    """RUN THE REAL THING. An argv that is well formed and wrong looks identical
    to one that works until a download is verified against it."""
    payload = b"rediacc toolchain platform differential\n"
    target = tmp_path / "payload.bin"
    target.write_bytes(payload)
    argv = plat.sha256_command()
    result = subprocess.run(
        [*argv, str(target)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.split()[0] == hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- Windows only ever points at a WSL launcher ---------------------------------------------------------------------------


@pytest.mark.parametrize("system", ["Windows", "MINGW64_NT-10.0-22631", "CYGWIN_NT-10.0"])
def test_windows_is_never_a_native_target(system: str) -> None:
    assert plat.runs_natively(system) is False
    with pytest.raises(plat.UnsupportedPlatformError) as excinfo:
        plat.require_native_host(system)
    for launcher in plat.WINDOWS_LAUNCHERS:
        assert launcher in str(excinfo.value)


@pytest.mark.parametrize("system", ["Linux", "Darwin"])
def test_linux_and_macos_are_native(system: str) -> None:
    """CONTROL. A `runs_natively` that returned False for everything would pass
    every case above."""
    assert plat.runs_natively(system) is True
    assert plat.require_native_host(system) == plat.os_name(system)


def test_the_launchers_the_refusal_names_exist() -> None:
    """A message pointing at a renamed file is worse than no message."""
    for launcher in plat.WINDOWS_LAUNCHERS:
        assert paths.from_root(launcher).is_file(), launcher


def test_the_windows_launcher_really_re_enters_wsl() -> None:
    """The claim in the refusal, checked against the artifact rather than assumed."""
    text = paths.from_root(RUN_PS1).read_text(encoding="utf-8")
    assert "wsl.exe" in text
    assert "--cd" in text


# ---------------------------------------------------------------------------
# the fix in the bash, pinned; each pattern with the control that it would catch
# a regression ---------------------------------------------------------------------------


def _url_lines() -> list[str]:
    text = paths.from_root(TOOLCHAIN_SH).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip().startswith("url=")]


def test_the_download_urls_derive_their_os() -> None:
    """Both asset URLs interpolate ${os}; neither carries a literal platform.

    This is the defect in its original form: a hardcoded `linux` in a URL whose arch WAS derived, which on an arm64 Mac downloaded a Linux binary that then passed its checksum. `os_name()` is what a caller uses instead.
    """
    lines = _url_lines()
    assert len(lines) >= 2, "no url= assignments found; the file has changed shape"
    for line in lines:
        assert "${os}" in line, line
        assert ".linux." not in line, line
        assert "_linux_" not in line, line


def test_the_url_pattern_would_catch_a_regression() -> None:
    """CONTROL. Without it the assertion above passes on any file that has no
    url= lines at all, or on a pattern that matches nothing."""
    planted = 'url="https://example.invalid/download/v${want}/tool-v${want}.linux.${arch}.tar.xz"'
    assert "${os}" not in planted
    assert ".linux." in planted


SHA_SHIM_OPEN = "_toolchain_sha256sum() {"


def _sha256_call_sites() -> list[str]:
    """Every live `sha256sum` line in toolchain.sh OUTSIDE the portable shim.

    The shim's own body is excluded, and that exclusion is the whole subtlety: `sha256sum "$@"` inside `_toolchain_sha256sum` is the CORRECT line -- it is the GNU rung of the ladder, guarded by the `command -v` above it. The first draft of this case flagged it, which is a scanner that cannot tell the fix
    from the defect. Comment lines are dropped for the same reason
    `check-toolchain-pins.sh` drops them: prose about a defect is not the defect.
    """
    text = paths.from_root(TOOLCHAIN_SH).read_text(encoding="utf-8")
    assert SHA_SHIM_OPEN in text, "the portable sha256 shim is gone from %s" % TOOLCHAIN_SH
    before, _, rest = text.partition(SHA_SHIM_OPEN)
    _shim_body, _, after = rest.partition("\n}\n")
    return [
        line.strip()
        for line in (before + after).splitlines()
        if "sha256sum" in line and not line.strip().startswith("#")
    ]


def test_the_checksum_verification_is_not_a_bare_sha256sum() -> None:
    """Its sibling defect, pinned. `sha256sum` is absent on macOS, where the
    caller's `|| { MISMATCH }` arm then fires for a reason that is not true."""
    sites = _sha256_call_sites()
    assert sites, "no sha256 call sites found outside the shim; the file has changed shape"
    for line in sites:
        assert "_toolchain_sha256sum" in line, line


def test_the_sha256_pattern_would_catch_a_regression() -> None:
    """CONTROL for the case above, on a planted line of the shape it must reject."""
    planted = 'echo "${sha}  ${bin}.tmp" | sha256sum -c - >/dev/null 2>&1 || {'
    assert "sha256sum" in planted
    assert "_toolchain_sha256sum" not in planted
    assert not planted.strip().startswith("#")


# --------------------------------------------------------------------------- the argv surface ---------------------------------------------------------------------------


def _module(*args: str):
    env = diff.env_for()
    env["PYTHONPATH"] = str(paths.ci_dir())
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.platform", *args],
        cwd=diff.repo(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_os_and_arch_agree_with_the_module() -> None:
    assert _module("os").stdout.strip() == plat.os_name()
    for scheme in sorted(plat.ARCH_NAMES):
        result = _module("arch", scheme)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == plat.arch_for(scheme)


def test_cli_os_takes_an_optional_scheme() -> None:
    """A bare `os` is the asset spelling; `os sea` is the artefact one."""
    assert _module("os", "sea").stdout.strip() == plat.os_for("sea")
    bad = _module("os", "posix")
    assert bad.returncode == 1
    assert bad.stdout == ""


def test_cli_arch_refuses_a_missing_or_unknown_scheme() -> None:
    """Nothing on stdout, so `a="$(...)" || die` cannot pick up a wrong arch."""
    for args in (("arch",), ("arch", "gnu-triplet")):
        result = _module(*args)
        assert result.returncode == 1
        assert result.stdout == ""
        assert result.stderr.strip()


def test_cli_uv_target_is_the_two_fields_bootstrap_reads() -> None:
    """`read -r triple sfx < <(uv_target)` at .ci/bootstrap.sh:172."""
    result = _module("uv-target")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == list(plat.uv_target())


def test_cli_wsl_answers_in_the_exit_code_and_names_the_signal() -> None:
    result = _module("wsl")
    assert result.returncode in (0, 1)
    assert result.returncode == (0 if plat.detect_wsl().is_wsl else 1)
    assert result.stdout.strip() == plat.detect_wsl().describe()


def test_cli_report_never_dies_partway() -> None:
    """Every line, even on a host missing a tool. A report that stops at line
    three is the least useful thing to hand someone diagnosing a host."""
    result = _module("report")
    assert result.returncode == 0, result.stderr
    keys = {line.split(":", 1)[0] for line in result.stdout.splitlines() if line}
    assert {"os", "machine", "sha256", "wsl", "native"} <= keys


def test_cli_unknown_verb_is_a_refusal() -> None:
    result = _module("uname")
    assert result.returncode == 1
    assert result.stdout == ""
