"""Which OS and which architecture, in the exact spellings this repo's URLs use.

WHAT IT REPLACES. FOURTEEN `case "$(uname -s)"` blocks and TWELVE `case "$(uname -m)"` blocks, spread across twelve tracked files, agreeing about nothing except that they all start from uname. Enumerated with `git grep -n 'case "$(uname -s)"' -- '*.sh'` on 2026-09-06, private/ excluded (the numbers in the first draft of this docstring were guessed from a partial
grep and were wrong in both directions; these are the grep's):

  OS, 14 sites
    .ci/scripts/lib/toolchain.sh:304    linux | darwin           (asset URL)
    .ci/bootstrap.sh:93                 unknown-linux-gnu | apple-darwin
    .ci/lib/setup.sh:97                 linux | darwin           (node tarball)
    .ci/lib/setup.sh:361                linux | darwin           (go tarball)
    .ci/lib/local-common.sh:794         MINGW | MSYS | CYGWIN    (.exe suffix)
    .ci/scripts/infra/build-renet.sh:32 MINGW | MSYS | CYGWIN    (.exe suffix)
    .ci/scripts/build/build-cli-executables.sh:61  linux | mac | win
    rdc.sh:89                           linux | mac | win        (SEA name)
    .ci/scripts/lib/common.sh:64        linux | macos | windows | unknown
    .ci/scripts/test/test-install-script.sh:58
    .ci/scripts/test/test-rdc-update.sh:157
    packages/www/public/install.sh:31, :89, :208

  arch, 12 sites
    .ci/scripts/lib/toolchain.sh:319    amd64 | arm64            (shfmt)
    .ci/scripts/lib/toolchain.sh:393    x86_64 | aarch64         (shellcheck)
    .ci/bootstrap.sh:101                x86_64 | aarch64         (uv triple)
    .ci/lib/setup.sh:105                x64 | arm64              (node tarball)
    .ci/lib/setup.sh:369                amd64 | arm64            (go tarball)
    .ci/lib/local-common.sh:489         amd64 | arm64            (go tarball)
    .ci/scripts/build/build-cli-executables.sh:75  x64 | arm64
    rdc.sh:107                          x64 | arm64              (SEA name)
    .devcontainer/start-vscode.sh:195   x64 | arm64
    .ci/scripts/test/test-install-script.sh:71
    .ci/scripts/test/test-rdc-update.sh:165
    packages/www/public/install.sh:98
  plus .ci/breakpoint/lib/breakpoint-common.sh:156, which cases on a variable
  it filled from uname a line earlier: x64 | arm64 | unknown.

THREE SPELLINGS OF THE SAME TWO ARCHITECTURES, and every one of them is right: they are the names three different UPSTREAMS publish their assets under. So this module does NOT invent a fourth. `ARCH_NAMES` below is a table keyed by the consumer, with the file and line each row was read from, and `arch_for()` is how a caller says which of the three it needs. A helper that returned
one "normalized arch" would be a fourth scheme that every call site then has to translate, which is how a fourth scheme starts.

TWO SPELLINGS OF THE OS, for the same reason and with the same treatment. The download URLs want `linux | darwin | windows`, and this repo's OWN artefact names want `linux | mac | win` (`rdc-mac-arm64`, `rdc-win-x64.exe`). `OS_NAMES` carries
both and `os_for()` selects; `os_name()` is the asset spelling, because that is
what every third-party URL in the tree asks for.

`.ci/scripts/lib/common.sh:64` is a THIRD spelling (`macos`, `windows`) and it is deliberately NOT a row here, because it also carries a fail-open default arm -- an unrecognised uname yields the string `unknown` rather than a refusal, and every caller then compares against a value that reads like an answer. Adopting it would import that behaviour. Reported to the driver rather than
reproduced.

--------------------------------------------------------------------------
THE DEFECT THIS MODULE IS SHAPED BY
--------------------------------------------------------------------------
`toolchain.sh` used to hardcode the literal string `linux` into both of its download URLs while deriving only the ARCH from uname. On an arm64 Mac that was not a 404, which is what made it dangerous: `uname -m` says arm64, the ARM64 checksum is present and matches, so a LINUX binary downloads, VERIFIES, gets chmod +x, and fails much later with "cannot execute binary file" from a
gate that has no idea it installed another OS's tool. `_toolchain_os` (toolchain.sh:303)
and `uv_target` (bootstrap.sh:91) are the bash fixes; `os_name()` and
`uv_target()` here are the same decision in one place, and `uv_target()` is checked byte for byte against the bash in the tests.

The sibling defect is `sha256sum`, which does not exist on macOS -- it is `shasum -a 256` there. Verifying with the bare GNU name on a Mac does not report "cannot verify", it reports a checksum MISMATCH that never happened, and the
caller's `|| { refuse }` arm fires for a reason that is not true. THREE copies of
that shim exist in the tree today (`_toolchain_sha256sum` at toolchain.sh:282, `sha256_of` at bootstrap.sh:123, `_sha256sum` at local-common.sh:37), each carrying a comment pointing at the other two. `sha256_command()` here is what a caller needs to stop writing a fourth: it returns the ARGV, so the caller spawns it, and it RAISES when neither tool exists rather than returning
something that reads as a verifier.

--------------------------------------------------------------------------
WINDOWS IS NEVER A NATIVE TARGET
--------------------------------------------------------------------------
Linux, WSL and macOS run this repo's toolchain directly. Windows does not, and the reason is recorded in run.ps1's own header rather than invented here: the toolchain is provisioned INSIDE WSL by `.ci/bootstrap.sh` and `./run.sh setup`, so the Windows entry points (`run.cmd` -> `run.ps1`) exist only to re-enter WSL
with `--cd` and propagate the exit code. `require_native_host()` therefore
refuses on Windows and names those two files, instead of letting a gate discover it by failing at `sha256sum` or at a path separator.

WSL IS LINUX, not a fourth OS. `os_name()` answers `linux` under WSL, because every download URL, every checksum key and every binary is the Linux one. WSL-ness is a SEPARATE question, answered separately, because what it changes is advice and not artifacts.

--------------------------------------------------------------------------
WSL DETECTION IS EVIDENCE, NOT A GUESS
--------------------------------------------------------------------------
`detect_wsl()` reads the kernel's own strings and REPORTS WHICH ONE FIRED:

    /proc/version                  the full kernel build banner. This is the
                                   signal `.ci/lib/setup.sh:588` already uses
                                   (`grep -qi microsoft /proc/version`) to tell
                                   a developer that a missing docker is really a
                                   Docker Desktop WSL-integration toggle.
    /proc/sys/kernel/osrelease     the release string alone, e.g.
                                   `5.15.167.4-microsoft-standard-WSL2`. Read as
                                   well as /proc/version because WSL2 kernels
                                   have been built without `Microsoft` in the
                                   banner while keeping it here.

Both are matched case-insensitively against `microsoft` and `wsl`.

$WSL_DISTRO_NAME and $WSL_INTEROP are recorded in `env_signals` and are DELIBERATELY NOT sufficient on their own. An environment variable is a claim: it is inherited by anything the shell spawns, it survives an `ssh` from a WSL host into a Linux VM, and `wsl.exe -- env` propagates it in the other direction. /proc is the kernel answering about itself. So `is_wsl` is decided by /proc
alone, and the env vars are carried for the diagnostic they are good at -- naming the distro in a message.

`proc_root` is a parameter so the tests can plant both files and assert on WHICH signal fired, in both directions, without needing a WSL host or a non-WSL one.

--------------------------------------------------------------------------
COMMAND-LINE ENTRY POINT (what a bash caller can reach)
--------------------------------------------------------------------------
    python3 -m rediacc_ci.core.platform os [scheme]
        linux | darwin | windows by default (the `asset` spelling, which is what
        every download URL wants); `os sea` gives linux | mac | win, the spelling
        this repo names its own executables with. Exit 1 and nothing on stdout
        when uname says something with no pinned build.

    python3 -m rediacc_ci.core.platform arch <scheme>
        scheme is one of goarch | uname | node. Exit 1 on an unknown scheme or
        an architecture with no pinned build.

    python3 -m rediacc_ci.core.platform uv-target
        "<triple> <SHA_VAR_SUFFIX>", the two fields `.ci/bootstrap.sh:172` reads
        with a single `read -r triple sfx`.

    python3 -m rediacc_ci.core.platform sha256
        the argv of a working sha256 tool, space separated. Exit 1 when there is
        none, so a caller cannot mistake absence for a mismatch.

    python3 -m rediacc_ci.core.platform wsl
        exit 0 under WSL and print the signals that fired; exit 1 otherwise.

    python3 -m rediacc_ci.core.platform report
        every answer above, one `key: value` per line, for a doctor output.
"""

from __future__ import annotations

import pathlib
import platform as _stdlib_platform
import sys

from rediacc_ci import proc

OS_LINUX = "linux"
OS_DARWIN = "darwin"
OS_WINDOWS = "windows"

# `uname -s` prefixes, mapped. The MINGW / MSYS / CYGWIN arms are not hypothetical: `.ci/lib/local-common.sh:795` and `rdc.sh:98` both branch on exactly those three to pick a `.exe` suffix, so Git Bash is a host this repo already meets. Matched by PREFIX because the real strings carry a version (`MINGW64_NT-10.0-22631`, `CYGWIN_NT-10.0`).
SYSTEM_PREFIXES = (
    ("Linux", OS_LINUX),
    ("Darwin", OS_DARWIN),
    ("Windows", OS_WINDOWS),
    ("MINGW", OS_WINDOWS),
    ("MSYS", OS_WINDOWS),
    ("CYGWIN", OS_WINDOWS),
)

# `uname -m` folded to ONE canonical key per architecture. The two spellings in each row are the pair every `case` in the tree already accepts (`x86_64 | amd64`, `aarch64 | arm64`), so this loses nothing.
MACHINE_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}

# THE THREE PUBLISHED SPELLINGS, each row read from the file that builds the URL.
# Do not add a fourth scheme; add a row when a fourth UPSTREAM appears.
#
# goarch Go's GOARCH, which is how mvdan.cc/sh and go.dev name their assets. shfmt_v3.13.1_linux_amd64 .ci/scripts/lib/toolchain.sh:339 go1.26.6.linux-amd64.tar.gz .ci/lib/setup.sh:378 uname the raw machine name, which is how koalaman/shellcheck and astral-sh/uv name theirs. shellcheck-v0.10.0.linux.x86_64.tar.xz .ci/scripts/lib/toolchain.sh:422 uv-x86_64-unknown-linux-gnu.tar.gz
# .ci/bootstrap.sh:182 node Node's own release naming, reused by this repo's SEA artefacts. node-v22.13.0-linux-x64.tar.xz .ci/lib/setup.sh:105 rdc-linux-x64 rdc.sh:98
ARCH_NAMES = {
    "goarch": {"x86_64": "amd64", "aarch64": "arm64"},
    "uname": {"x86_64": "x86_64", "aarch64": "aarch64"},
    "node": {"x86_64": "x64", "aarch64": "arm64"},
}

# THE TWO OS SPELLINGS, same treatment as ARCH_NAMES and for the same reason.
#
# asset what every third-party download URL in the tree asks for. shfmt_v3.13.1_darwin_arm64 .ci/scripts/lib/toolchain.sh:339 go1.26.6.linux-amd64.tar.gz .ci/lib/setup.sh:378 sea what THIS repo names its own executables, which is a different set of words for the same three systems and cannot be derived from the first by any rule. rdc-mac-arm64, rdc-win-x64.exe rdc.sh:89,
# .ci/scripts/build/build-cli-executables.sh:61
OS_NAMES = {
    "asset": {OS_LINUX: "linux", OS_DARWIN: "darwin", OS_WINDOWS: "windows"},
    "sea": {OS_LINUX: "linux", OS_DARWIN: "mac", OS_WINDOWS: "win"},
}

# The executable suffix per OS, which travels with the `sea` spelling and is the other half of what `.ci/lib/local-common.sh:795` and `.ci/scripts/infra/build-renet.sh:32` each derive by hand.
EXE_SUFFIXES = {OS_LINUX: "", OS_DARWIN: "", OS_WINDOWS: ".exe"}

# uv names its assets by target triple, so the OS half of the checksum key is also the OS half of the URL. Mirrors `uv_target` at .ci/bootstrap.sh:91-116.
UV_OS_TRIPLES = {OS_LINUX: "unknown-linux-gnu", OS_DARWIN: "apple-darwin"}

# The OSes whose toolchain this repo provisions and runs directly.
NATIVE_OSES = (OS_LINUX, OS_DARWIN)

# The two Windows front doors, in the order one calls the other. Named so the refusal below can point at them instead of describing them.
WINDOWS_LAUNCHERS = ("run.cmd", "run.ps1")

# The kernel files that ANSWER the WSL question, most specific first so the reported signal is the more precise one when both fire.
WSL_PROC_FILES = ("proc/sys/kernel/osrelease", "proc/version")

# Matched case-insensitively. Both markers, because WSL2 kernels have shipped
# with `WSL2` in osrelease and no `Microsoft` in the /proc/version banner.
WSL_MARKERS = ("microsoft", "wsl")

# Carried for diagnostics, never for the verdict. See the module docstring.
WSL_ENV_VARS = ("WSL_DISTRO_NAME", "WSL_INTEROP", "WSLENV")

# The portable sha256 ladder, in the order all three bash copies try it.
SHA256_COMMANDS = (("sha256sum",), ("shasum", "-a", "256"))


class PlatformError(RuntimeError):
    """This host is not one the repo has a pinned answer for.

    A distinct type so a caller can tell "no build exists for you" from any other failure without matching a message string.
    """


class UnsupportedPlatformError(PlatformError):
    """uname named an OS or an architecture with no pinned build."""


class MissingToolError(PlatformError):
    """A tool the caller cannot proceed without is on no PATH entry.

    SEPARATE FROM UnsupportedPlatformError on purpose. "macOS has no sha256sum" is a supported platform missing one binary, and reporting it as an unsupported platform is how the original defect read: a verifier that could not run reported as a verifier that had failed.
    """


def os_name(system: str | None = None) -> str:
    """linux | darwin | windows, from `uname -s`. Raises UnsupportedPlatformError.

    WSL answers `linux`, deliberately: every artefact it downloads is the Linux one. Ask `detect_wsl()` when the question is about advice rather than about a URL.
    """
    raw = _stdlib_platform.system() if system is None else system
    for prefix, name in SYSTEM_PREFIXES:
        if raw.startswith(prefix):
            return name
    raise UnsupportedPlatformError(
        "platform: unsupported OS %r -- no pinned build of this repo's toolchain "
        "exists for it (known: %s)" % (raw, ", ".join(p for p, _ in SYSTEM_PREFIXES))
    )


def os_for(scheme: str, system: str | None = None) -> str:
    """This host's OS in one consumer's spelling. Raises UnsupportedPlatformError.

    `scheme` is required and has no default, exactly as in `arch_for()`: `darwin` and `mac` name the same system and are not interchangeable, and a default would put the wrong one into either a download URL or an artefact name.
    """
    if scheme not in OS_NAMES:
        raise UnsupportedPlatformError(
            "platform: unknown OS scheme %r (known: %s)" % (scheme, ", ".join(sorted(OS_NAMES)))
        )
    return OS_NAMES[scheme][os_name(system)]


def exe_suffix(system: str | None = None) -> str:
    """`.exe` on Windows, empty elsewhere. Raises UnsupportedPlatformError.

    The other half of the `sea` spelling. `.ci/lib/local-common.sh:795` and `.ci/scripts/infra/build-renet.sh:32` each derive this from their own MINGW/MSYS/CYGWIN case, which is two copies of one fact.
    """
    return EXE_SUFFIXES[os_name(system)]


def machine_key(machine: str | None = None) -> str:
    """`uname -m` folded to x86_64 | aarch64. Raises UnsupportedPlatformError.

    The refusal is the important half. Every bash `case` in the tree ends its arch block with an explicit failure and a message that says "add a checksum
    rather than downloading unverified"; falling through to a default would
    download an asset for an architecture nobody recorded a hash for.
    """
    raw = (_stdlib_platform.machine() if machine is None else machine).strip().lower()
    if raw not in MACHINE_ALIASES:
        raise UnsupportedPlatformError(
            "platform: unsupported architecture %r -- add its checksum to "
            ".devcontainer/toolchain.env rather than downloading unverified "
            "(known: %s)" % (raw, ", ".join(sorted(MACHINE_ALIASES)))
        )
    return MACHINE_ALIASES[raw]


def arch_for(scheme: str, machine: str | None = None) -> str:
    """This host's architecture in one upstream's spelling. Raises on both axes.

    `scheme` is required and has no default, for the same reason `pin()` has no
    `default=`: the three spellings are not interchangeable, and a default would
    hand `x86_64` to a caller building a shfmt URL that needs `amd64`. The 404 would name GitHub.
    """
    if scheme not in ARCH_NAMES:
        raise UnsupportedPlatformError(
            "platform: unknown arch scheme %r (known: %s)" % (scheme, ", ".join(sorted(ARCH_NAMES)))
        )
    return ARCH_NAMES[scheme][machine_key(machine)]


def uv_target(system: str | None = None, machine: str | None = None) -> tuple[str, str]:
    """(target triple, checksum-key suffix) for the uv release asset.

    Byte for byte what `uv_target` in `.ci/bootstrap.sh:91` prints, split into the two fields that file reads with `read -r triple sfx` (bootstrap.sh:172). The suffix completes the pins-file key: `UV_SHA256_<suffix>`, which is the form `.devcontainer/toolchain.env` records all four of them under.
    """
    name = os_name(system)
    if name not in UV_OS_TRIPLES:
        raise UnsupportedPlatformError(
            "platform: uv publishes no pinned build this repo records for %s" % name
        )
    key = machine_key(machine)
    triple = "%s-%s" % (ARCH_NAMES["uname"][key], UV_OS_TRIPLES[name])
    return triple, "%s_%s" % (name.upper(), key.upper())


def uv_checksum_key(system: str | None = None, machine: str | None = None) -> str:
    """The pins-file key holding this host's uv checksum, e.g. UV_SHA256_LINUX_X86_64."""
    return "UV_SHA256_%s" % uv_target(system, machine)[1]


class WslEvidence:
    """What the kernel said, and which file said it.

    An object rather than a bool because "is this WSL" is only half the answer a caller needs: a message that says WHICH signal fired is the difference between a developer trusting the detection and re-checking it by hand. Slots rather than a dataclass to match `age.Verdict` next door.
    """

    __slots__ = ("distro", "env_signals", "signals")

    def __init__(
        self,
        signals: tuple[tuple[str, str], ...] = (),
        env_signals: tuple[str, ...] = (),
        distro: str = "",
    ) -> None:
        self.signals = signals
        self.env_signals = env_signals
        self.distro = distro

    @property
    def is_wsl(self) -> bool:
        """Decided by /proc alone. See the module docstring on why not by env."""
        return bool(self.signals)

    def describe(self) -> str:
        """One line naming every signal, or saying plainly that none fired."""
        if not self.signals:
            return "not WSL: no marker in %s" % ", ".join("/" + f for f in WSL_PROC_FILES)
        return "WSL: " + "; ".join(
            "/%s matched %r" % (source, marker) for source, marker in self.signals
        )


def detect_wsl(proc_root: pathlib.Path | str = "/", env: dict[str, str] | None = None):
    """Read the kernel's own strings and report which ones name WSL.

    `proc_root` is a parameter so a test can plant `proc/version` and `proc/sys/kernel/osrelease` under a tmpdir and assert on WHICH signal fired, in both directions, on any host. Without that the case could only be written as "whatever this machine is", which asserts nothing.

    An unreadable file is not a signal and not an error: /proc is absent on macOS, and `detect_wsl()` there must answer "not WSL" rather than raise.
    """
    import os  # noqa: PLC0415 -- stdlib os is used by this function alone

    root = pathlib.Path(proc_root)
    environ = os.environ if env is None else env

    signals: list[tuple[str, str]] = []
    for relative in WSL_PROC_FILES:
        try:
            text = (root / relative).read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        for marker in WSL_MARKERS:
            if marker in text:
                signals.append((relative, marker))
                break

    env_signals = tuple(name for name in WSL_ENV_VARS if environ.get(name))
    return WslEvidence(tuple(signals), env_signals, environ.get("WSL_DISTRO_NAME", ""))


def runs_natively(system: str | None = None) -> bool:
    """Does this repo's toolchain run directly here? False on Windows only."""
    return os_name(system) in NATIVE_OSES


def require_native_host(system: str | None = None) -> str:
    """The OS name, or a refusal that names the WSL launchers. Raises.

    The refusal exists so a Windows caller is told the ONE thing that helps -- go in through run.cmd, which re-enters WSL -- rather than discovering it as a missing `sha256sum`, a `.exe` that is not there, or a path separator.
    """
    name = os_name(system)
    if name not in NATIVE_OSES:
        raise UnsupportedPlatformError(
            "platform: %s is not a native target for this repo's toolchain. It is "
            "provisioned inside WSL by .ci/bootstrap.sh and ./run.sh setup; enter "
            "through %s, which re-enters WSL with the right working directory and "
            "propagates the exit code." % (name, " -> ".join(WINDOWS_LAUNCHERS))
        )
    return name


def sha256_command(env: dict[str, str] | None = None) -> list[str]:
    """The argv of a working sha256 tool. Raises MissingToolError when there is none.

    THE ARGV, not the digest, because the three bash copies this replaces are all invoked in different shapes -- `... -c -` against a planted line, `... file | cut -d' ' -f1`, and a pipeline stdin form -- and a function that computed a
    digest would serve none of them. Python callers should use `hashlib`; this is
    for the shell.

    RAISES rather than returning `["sha256sum"]` and hoping. That distinction is the entire defect: on macOS the bare GNU name is "command not found", the
    caller's `|| { checksum MISMATCH }` arm fires, and a download is refused for
    a mismatch that never happened.
    """
    for argv in SHA256_COMMANDS:
        if proc.which(argv[0], env=env):
            return list(argv)
    raise MissingToolError(
        "platform: no sha256 tool on PATH (need %s) -- cannot verify a download. "
        "A verifier that cannot run must not read as a verifier that failed."
        % " or ".join(argv[0] for argv in SHA256_COMMANDS)
    )


def report(system: str | None = None, machine: str | None = None) -> list[str]:
    """`key: value` lines for a doctor output. Never raises.

    Every answer is caught individually: a host with no `shasum` must still be able to print its OS and its architecture, and a report that dies on its third line is the least useful thing to hand someone diagnosing a host.
    """
    lines = []
    for key, fetch in (
        ("os", lambda: os_name(system)),
        ("os.sea", lambda: os_for("sea", system)),
        ("exe", lambda: exe_suffix(system) or "(none)"),
        ("machine", lambda: machine_key(machine)),
        ("arch.goarch", lambda: arch_for("goarch", machine)),
        ("arch.uname", lambda: arch_for("uname", machine)),
        ("arch.node", lambda: arch_for("node", machine)),
        ("uv.target", lambda: uv_target(system, machine)[0]),
        ("uv.checksum-key", lambda: uv_checksum_key(system, machine)),
        ("sha256", lambda: " ".join(sha256_command())),
        ("native", lambda: "yes" if runs_natively(system) else "no"),
        ("wsl", lambda: detect_wsl().describe()),
    ):
        try:
            lines.append("%s: %s" % (key, fetch()))
        except PlatformError as exc:
            lines.append("%s: UNAVAILABLE (%s)" % (key, exc))
    return lines


# --------------------------------------------------------------------------- argv dispatch -- the surface a bash caller reaches ---------------------------------------------------------------------------


def _fail(message: str) -> int:
    """Message on STDERR, nothing on stdout, exit 1.

    Same contract as `core.toolchain._fail`: every bash caller reads these verbs
    with `v="$(...)"`, so a diagnostic on stdout would be captured into the
    variable and interpolated into whatever the value was for.
    """
    print(message, file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: python3 -m rediacc_ci.core.platform <verb> [args]",
            file=sys.stderr,
        )
        return 2
    verb, rest = argv[0], argv[1:]

    if verb == "wsl":
        # The verdict is the EXIT CODE, so a caller writes `if ... wsl; then`.
        # The signals go to stdout either way, because the reason is the useful part in both directions.
        evidence = detect_wsl()
        print(evidence.describe())
        return 0 if evidence.is_wsl else 1

    if verb == "report":
        for line in report():
            print(line)
        return 0

    try:
        if verb == "os":
            # A bare `os` keeps the asset spelling, which is what every URL in
            # the tree wants; `os sea` asks for the artefact spelling.
            print(os_for(rest[0]) if rest else os_name())
        elif verb == "machine":
            print(machine_key())
        elif verb == "arch":
            if not rest:
                return _fail("platform: arch needs a scheme (%s)" % ", ".join(sorted(ARCH_NAMES)))
            print(arch_for(rest[0]))
        elif verb == "uv-target":
            print("%s %s" % uv_target())
        elif verb == "sha256":
            print(" ".join(sha256_command()))
        elif verb == "native":
            if runs_natively():
                return 0
            return _fail(
                "platform: %s is not a native target; enter through %s"
                % (os_name(), " -> ".join(WINDOWS_LAUNCHERS))
            )
        else:
            return _fail("unknown verb: %s" % verb)
    except PlatformError as exc:
        return _fail(str(exc))
    return 0


__all__ = [
    "ARCH_NAMES",
    "EXE_SUFFIXES",
    "MACHINE_ALIASES",
    "NATIVE_OSES",
    "OS_DARWIN",
    "OS_LINUX",
    "OS_NAMES",
    "OS_WINDOWS",
    "SHA256_COMMANDS",
    "SYSTEM_PREFIXES",
    "UV_OS_TRIPLES",
    "WINDOWS_LAUNCHERS",
    "WSL_ENV_VARS",
    "WSL_MARKERS",
    "WSL_PROC_FILES",
    "MissingToolError",
    "PlatformError",
    "UnsupportedPlatformError",
    "WslEvidence",
    "arch_for",
    "detect_wsl",
    "exe_suffix",
    "machine_key",
    "os_for",
    "os_name",
    "report",
    "require_native_host",
    "runs_natively",
    "sha256_command",
    "uv_checksum_key",
    "uv_target",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
