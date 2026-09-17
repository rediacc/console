#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-cli-executables.sh`.

Builds the `rdc` CLI as a Node.js Single Executable Application: bundle the CJS, prepare the embedded renet assets, generate the SEA blob, copy the host `node` binary, strip it, inject the blob, verify the injection, checksum it, and -- when the build is NATIVE rather than cross -- smoke-test the result with `--version` and `doctor --output json`.

Driven per-platform by `.github/workflows/ci-build-cli.yml`; every artifact CD ever promotes comes out of this script.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT, because the twin shells out to it and the call is the observable:

  * `uname -s` / `uname -m`. FOUR call sites, and the count is observable, so
    they are real subprocesses here rather than `platform.system()`. Two are the
    twin's own inline auto-detect `case`s (:61, :75); two are `detect_os` and
    `detect_arch` from `common.sh` (:63-72, :98-106) inside the smoke-test guard
    at :243. `rediacc_ci.core.common.detect_os()` answers the same question from
    `platform.system()` WITHOUT a subprocess, and using it would make the port
    unfalsifiable against a fixture that fakes `uname` -- which is exactly how
    the mac and win branches below are exercised, since this machine is Linux.
  * `node`, five times, with distinct argv: `--version`, `bundle.mjs`,
    `--experimental-sea-config`, `sea-inject/cli.mjs`, `sea-inject/verify.mjs`.
  * `.ci/scripts/build/prepare-cli-assets.sh`, by the same absolute path the twin
    builds from `$SCRIPT_DIR`. It has its OWN port (`build/prepare_cli_assets.py`)
    and this file deliberately does not call it: the twin invokes the BASH one, so
    calling the Python one would make the two sides run different programs and
    the differential would be comparing the ports to each other.
  * `cp`, `chmod +x`, `strip --strip-all`, `codesign`, `sha256sum`/`shasum`, `jq`.
    `cp` and `chmod` are shelled out rather than done with `shutil`/`os.chmod`
    because `chmod +x` is `a+x` MASKED BY THE UMASK and `cp` creates with the
    umask too; reimplementing that is reimplementing a umask, and the artifact
    mode is compared.

NOT SHELLED OUT, and each for a stated reason:

  * `wc -c <file` (four sites) -> `Path.stat().st_size`. `wc -c` under a redirect
    prints the byte count and nothing else; the digits are identical and adding
    a `wc` process would put a line in a call log the twin's `wc` would also put
    there, so faking it proves nothing.
  * `cat "$OUTPUT_DIR/${BINARY_NAME}.sha256"` inside `$( )` -> a file read with
    trailing newlines stripped, which is what command substitution does.
  * `mkdir -p` -> `Path.mkdir(parents=True, exist_ok=True)`, same umask, same
    result, no observable process.
  * `sed 's/macos/mac/; s/windows/win/'` at :243 -> two `str.replace` calls. It is
    a pure rename of `detect_os`'s vocabulary into this script's, applied to a
    string this file already holds.
  * `.ci/scripts/version/inject-env.sh`, which the twin SOURCES (:130, :136).
    Sourcing is the whole point: it exports `APP_VERSION`, `VITE_APP_VERSION`,
    `CLI_VERSION` and `TAG` into the shell that then runs `node bundle.mjs`. A
    subprocess could not do that, so this port calls
    `rediacc_ci.version.inject_env.inject()` -- the already-ported twin of that
    file, whose `inject()` returns `(code, exports, stdout, stderr)` precisely so
    a sourcing caller has something to source -- and applies `exports` to
    `os.environ`. Reimplementing the version resolution here would be a second
    place the release-version rule is written down.

-----------------------------------------------------------------------------
WHY THE PROCESS REALLY chdir()s
-----------------------------------------------------------------------------
`:143` is a bare `cd "$CLI_DIR"` and everything after it is relative: `node bundle.mjs`, `wc -c <dist/cli-bundle.cjs`, `sea-config.generated.json`, and -- this is the part that matters -- `$OUTPUT_DIR` itself when the caller passed a RELATIVE `--output`. Resolving `--output` against the invocation directory would be a nicer program and a different one, so `main()` calls
`os.chdir()` and every path below it stays exactly as textual as the twin's.

-----------------------------------------------------------------------------
FIVE REAL DEFECTS IN THE TWIN, REPRODUCED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
`.ci/scripts/build/` is not this wave's to edit; each of these is carried and pinned in `tests/test_build_cli_executables.py` so a later cutover can decide.

DEFECT 1 -- A MISSING `node` IS A SILENT EXIT 1. `:99` is
`NODE_BIN="$(command -v node)"`, an assignment whose command substitution fails
when `node` is absent, so `set -e` kills the script BEFORE the first `log_step`.
Driven: zero bytes on stdout, zero on stderr, `rc=1`. There is no `require_cmd
node` anywhere in the file, and `require_cmd` is exactly the helper that would have printed "Required command 'node' is not available". A build agent whose node install failed gets a step that looks like a gate failing for a real reason. `node_bin()` below returns `None` and `main()` returns 1 printing nothing.

DEFECT 2 -- `strip` AND `codesign` ARE NEVER DECLARED EITHER. `:175` and `:167`/`:221` invoke them bare under `set -e`, so a runner without binutils dies at `strip: command not found`, rc 127, in the middle of a step whose last line said "Stripping debug symbols...". Same class as DEFECT 1, one rung louder because bash at least names the command.

DEFECT 3 -- "NO CHECKSUM TOOL" IS A WARNING, NOT A REFUSAL. `:236` warns and continues when neither `sha256sum` nor `shasum` exists, and `:238` then finds no `.sha256` file and simply does not print a checksum line. The build exits 0 having published a binary with no checksum beside it, and the only trace is one `⚠` in a log nobody reads. Reproduced verbatim.

DEFECT 4 -- THE `--version` SMOKE TEST CANNOT TELL A SIGNAL FROM A VERDICT, WHILE THE `doctor` ONE CAN. `:332-336` goes out of its way to decode 128<rc<160 as "KILLED by signal N", with a comment explaining why that matters. `:251`, twelve lines earlier, prints `Smoke test (--version) failed (exit code: 137)` for the identical case. The asymmetry is carried, not smoothed.

DEFECT 5 -- AN UNRECOGNISED `--platform` IS ACCEPTED. The auto-detect `case`s at
:61 and :75 refuse a platform they cannot name, but an EXPLICIT `--platform
banana` is never validated: the run proceeds, names the artifact `rdc-banana-x64`, skips the mac and linux arms, and the smoke-test guard at :243 compares `banana` against `linux` and quietly reports "Skipping smoke tests (cross-platform build)". So the one arm that would have caught it is the arm the typo disables. Reproduced; `test_an_unvalidated_platform_builds_a_nonsense_name`
pins it.

-----------------------------------------------------------------------------
ONE DIVERGENCE THAT IS A DECISION
-----------------------------------------------------------------------------
`cd`'s own failure diagnostic. `:143`'s `cd "$CLI_DIR"` on a missing directory prints `<twin path>: line 143: cd: <dir>: No such file or directory`; the faithful analogue names THIS file and THIS line, computed from the live frame so it cannot go stale. The `<path>: line <n>: ` prefix is masked in the differential and the tail is compared verbatim, the same treatment
`build_linux_packages.py`
gives its `${NEXT_VERSION:?}` diagnostic.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE
-----------------------------------------------------------------------------
`os.environ.get("RELEASE_BUILD", "")` and `os.environ.get("CLI_VERSION", "")`, spelled out where they are used. No dict alias and no loop: the env-manifest reader parses direct `os.environ` reads by name, and an alias makes the name invisible to it (confirmed four times across this campaign).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.version import inject_env

# `:198`. The fuse sentinel node's runtime looks for; passed to both the injector and the verifier so a mismatch between them is impossible by construction.
SENTINEL_FUSE = "NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2"

# `:196`. The section/note name the blob is injected under.
BLOB_NAME = "NODE_SEA_BLOB"

# `:201`. Retained "for argv parity" (the twin's words): the Mach-O backend fixes the segment name internally, so the flag changes nothing except the argv a reader sees.
MACHO_SEGMENT_NAME = "NODE_SEA"

# `:107`, `:124`. The literal both flags are compared against; `[[ x == "true" ]]`
# is a string test, so `RELEASE_BUILD=1` is NOT a release build.
TRUE = "true"

# `:136`. The placeholder a non-release build falls back to. Spelled here once, exactly as the twin spells it once, because the whole point of routing through inject-env is that the fallback lives in one place.
DEV_VERSION = "0.0.0-dev"

# `:261`. Doctor is ALLOWED to fail up to and including this code: CI has no auth and no renet, so a clean "some checks failed" verdict is the expected outcome.
DOCTOR_MAX_OK_EXIT = 2

# `:332`. The window bash uses for "killed by signal N": 128+1 .. 128+31.
SIGNAL_EXIT_LOW = 128
SIGNAL_EXIT_HIGH = 160

# `:273`. What `doctor` must report as the install method for a SEA build.
EXPECTED_INSTALL_METHOD = "SEA binary"

# `:297`. What the Node.js environment check must report.
EXPECTED_NODE_STATUS = "ok"

# `:313`. The literal prefix `verifyEmbeddedRenetIntegrity` writes on a corrupt read-back. The twin's comment records that this is a literal emitted by the CLI itself, which is what makes the match locale-independent.
CORRUPT_PREFIX = "corrupt"


class Refusal(Exception):  # noqa: N818 - named for what the twin does, not for Error
    """A `log_error ...; exit N` in the twin.

    Carries the stderr lines already formatted and the status to exit with, so `main()` has exactly one place that prints and returns. The twin can afford a bare `exit` because it is a script; a module that other code imports cannot.

    `raw=True` marks the lines bash itself wrote rather than `log_error`: an
    unbound-variable death and a "command not found" carry NO `✗` glyph, because the shell printed them before any of the script's own code ran. Folding those two shapes into one would put a tick-mark on a message the twin emits bare.
    """

    def __init__(self, code: int, *lines: str, raw: bool = False) -> None:
        super().__init__(lines[0] if lines else "")
        self.code = code
        self.lines = lines
        self.raw = raw


def console_root() -> pathlib.Path:
    """The repository root, from this file's own location.

    Same derivation and same reasoning as `build/build_linux_packages.py`: the twin uses `get_repo_root` (`common.sh:205-210`), which has NO environment override, so `rediacc_ci.paths.repo_root()` -- which honours `$REDIACC_CI_ROOT` -- is deliberately not used. A differential in which one side follows an override and the other does not diverges for a reason that says nothing about
    the port.
    """
    # This file: <root>/.ci/rediacc_ci/build/build_cli_executables.py
    return pathlib.Path(__file__).resolve().parents[3]


def script_dir(root: pathlib.Path) -> pathlib.Path:
    """`$SCRIPT_DIR` -- `.ci/scripts/build`, where the BASH twin lives.

    Not this file's directory. `prepare-cli-assets.sh`, `sea-inject/cli.mjs` and `sea-inject/verify.mjs` are siblings of the TWIN, and their paths appear in the argv of real subprocesses, so both sides must name the same three files.
    """
    return root / ".ci" / "scripts" / "build"


def _capture(argv: list[str]) -> str:
    """`$(cmd)` -- stdout with trailing newlines stripped, stderr passed through.

    A command substitution that FAILS is not an error in bash unless it is the whole right-hand side of an assignment (see DEFECT 1); in every other position the shell takes the output it got and carries on. A missing binary therefore yields the empty string, which is what `case "$(uname -s)"` sees and what makes the twin's `Cannot detect platform from: ` message end in a space.
    Reproduced by returning "" on OSError rather than raising.
    """
    try:
        proc = subprocess.run(argv, capture_output=False, stdout=subprocess.PIPE, check=False)
    except OSError:
        return ""
    text = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    return text.rstrip("\n")


def uname(flag: str) -> str:
    """`$(uname -s)` / `$(uname -m)`, as a real subprocess. See the module head."""
    return _capture(["uname", flag])


def platform_from_uname(system: str) -> str | None:
    """`:61-69` -- the twin's own `case`, glob semantics included.

    `Linux*` is a PATTERN, not an equality test, so `Linux-something` is Linux. `Darwin*` likewise. The Windows arm is three patterns. Anything else is the `*)` arm, which refuses; returning `None` is that arm.
    """
    if system.startswith("Linux"):
        return "linux"
    if system.startswith("Darwin"):
        return "mac"
    if system.startswith(("MINGW", "MSYS", "CYGWIN")):
        return "win"
    return None


def arch_from_uname(machine: str) -> str | None:
    """`:75-82` -- EXACT alternatives, not globs, unlike the platform case above.

    `x86_64|amd64` and `aarch64|arm64` carry no `*`, so `x86_64h` (a real Darwin value on Haswell) falls through to the refusal. That asymmetry with `platform_from_uname` is the twin's, and it is carried.
    """
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    return None


def detect_os() -> str:
    """`common.sh:63-72`. A THIRD spelling: `macos`/`windows`, and `unknown`.

    Not `platform_from_uname` with a rename: this one has a FAIL-OPEN default arm that returns the string `unknown`, and `unknown` reads like an answer at the comparison site. `core.platform` refused to carry this function for that very reason; here the twin's caller compares against it, so it has to exist.
    """
    system = uname("-s")
    if system.startswith("Linux"):
        return "linux"
    if system.startswith("Darwin"):
        return "macos"
    if system.startswith(("CYGWIN", "MINGW", "MSYS")):
        return "windows"
    return "unknown"


def detect_arch() -> str:
    """`common.sh:98-106`. `x64`/`arm64`/`unknown`, same fail-open default."""
    machine = uname("-m")
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    return "unknown"


def native_platform_name() -> str:
    """`detect_os | sed 's/macos/mac/; s/windows/win/'` (`:243`).

    Two substitutions, applied in order, each unanchored and non-global -- which
    for these two inputs is indistinguishable from an exact rename, since neither
    `macos` nor `windows` can occur twice in `detect_os`'s four possible answers.
    """
    return detect_os().replace("macos", "mac").replace("windows", "win")


def source_common() -> None:
    """`common.sh:504-514` -- what SOURCING the library does before line 22 runs.

    FOUND BY THE CALL LOG, NOT BY READING. The first differential run of this port showed the twin invoking `uname -s` and `uname -m` before it had parsed a single argument, including on `--help`. The reason is that common.sh's INITIALIZATION block is not a function:

        CI_OS="$(detect_os)"
        CI_ARCH="$(detect_arch)"
        CI_TEMP="$(get_temp_dir)"
        export CI_OS CI_ARCH CI_TEMP

    So every one of the 208 files that sources it pays two `uname` processes at startup and hands three variables to every child it spawns. A port that skipped this would launch `node bundle.mjs` with `CI_OS` UNSET, which is a different environment for a build, not merely a different call count.

    `get_temp_dir` (`common.sh:115-123`) is `$RUNNER_TEMP`, else `$TMPDIR`, else `/tmp`, and needs no subprocess. Its `:-` semantics mean an EMPTY `RUNNER_TEMP` falls through, which is why these are truthiness tests.

    DUPLICATED IN THIS WAVE'S OTHER TWO PORTS ON PURPOSE. All three twins source common.sh, all three need this, and a shared home for it would be a fourth file this wave does not own. Named here so the cutover can lift it into `rediacc_ci.core.common` once, rather than discovering three copies. `core.common.ci_env()` is close but computes the OS from `platform.system()` rather
    than from a `uname` process, so it cannot stand in for a comparison whose whole point is the process.
    """
    os.environ["CI_OS"] = detect_os()
    os.environ["CI_ARCH"] = detect_arch()
    os.environ["CI_TEMP"] = (
        os.environ.get("RUNNER_TEMP", "") or os.environ.get("TMPDIR", "") or "/tmp"
    )


def binary_name(platform_name: str, arch: str) -> str:
    """`:93-96`. `rdc-<platform>-<arch>`, plus `.exe` for win and nothing else.

    Exported so the naming can be asserted without a build. Note that no validation happens here or anywhere: DEFECT 5 lives in what this function is willing to be handed.
    """
    name = "rdc-%s-%s" % (platform_name, arch)
    return name + ".exe" if platform_name == "win" else name


def parse_args(argv: list[str]) -> tuple[str, str, str, bool, str | None]:
    """`:30-57`. Returns `(platform, arch, output_dir, dry_run, help_line)`.

    `help_line` is non-None only for `-h`/`--help`, which prints to STDOUT and exits 0; the caller supplies `$0` because bash's `$0` is the path as invoked, not a resolved one.

    A flag whose value is missing is NOT handled here. `"$2"` under `set -u` is an unbound-variable death in the shell itself, with a diagnostic naming the script and the line, and `main()` reproduces that with the twin's line numbers (33, 37, 41) so the message is the same shape.
    """
    platform_name = ""
    arch = ""
    output_dir = ""
    dry_run = False
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        if flag == "--platform":
            platform_name = _value(rest, 33)
        elif flag == "--arch":
            arch = _value(rest, 37)
        elif flag == "--output":
            output_dir = _value(rest, 41)
        elif flag == "--dry-run":
            dry_run = True
        elif flag in ("-h", "--help"):
            return platform_name, arch, output_dir, dry_run, "help"
        else:
            # `*)` -- the arm every argument parser in this tree is checked for having, and this one has it.
            raise Refusal(1, "Unknown option: %s" % flag)
    return platform_name, arch, output_dir, dry_run, None


def _value(rest: list[str], line: int) -> str:
    """`"$2"` under `set -u`, including the death when there is no `$2`.

    bash writes `<script>: line <n>: $2: unbound variable` and exits 1 from the SHELL, not from the script's own logic, so there is no `✗` glyph and no log_error. The twin's line numbers are passed in rather than derived, because they are the twin's lines and drifting them would be silently wrong.
    """
    if not rest:
        raise Refusal(1, "%s: line %d: $2: unbound variable" % (sys.argv[0], line), raw=True)
    return rest.pop(0)


def node_bin() -> str | None:
    """`:99`, `NODE_BIN="$(command -v node)"`, and DEFECT 1 with it.

    Returns `None` when `node` is not on PATH. The caller's only correct response is to exit 1 printing NOTHING, because that is precisely what `set -e` does to an assignment whose command substitution failed.
    """
    return shutil.which("node")


def _size(path: str | pathlib.Path) -> int:
    """`$(wc -c <path)`. See the module head for why this is not a subprocess."""
    return pathlib.Path(path).stat().st_size


def require_file(path: str) -> None:
    """`common.sh:151-157`, verbatim message and status."""
    if not pathlib.Path(path).is_file():
        raise Refusal(1, "Required file '%s' does not exist" % path)


def _exec_failure(command: str, line: int) -> tuple[str, int]:
    """bash's OWN diagnostic when it cannot execute something, and its status.

    Two distinct shapes, and which one you get depends on the command WORD, not on the reason:

        strip                 -> `<$0>: line N: strip: command not found`, 127
        /path/that/is/absent  -> `<$0>: line N: /path: No such file or directory`, 127
        /path/not/executable  -> `<$0>: line N: /path: Permission denied`, 126

    A word containing a slash is a PATH and bash reports the errno for it; a bare word is a PATH SEARCH and bash reports that the search found nothing. This is reproduced rather than collapsed because DEFECT 2 -- an undeclared `strip` -- is diagnosed only by this message, and a port that printed the other shape would be describing a different failure than the one that happens.
    """
    if "/" in command:
        target = pathlib.Path(command)
        if target.exists():
            return "%s: line %d: %s: Permission denied" % (sys.argv[0], line, command), 126
        return "%s: line %d: %s: No such file or directory" % (sys.argv[0], line, command), 127
    return "%s: line %d: %s: command not found" % (sys.argv[0], line, command), 127


def _status(argv: list[str], line: int, **kw) -> int:
    """Run a command the way an `if cmd; then` condition does.

    bash's own exec failures are part of the contract: the shell DIAGNOSES them on stderr before the caller ever sees a status, and the twin's smoke-test arms branch on exactly the numbers `_exec_failure` returns.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(argv, check=False, **kw).returncode
    except OSError:
        message, code = _exec_failure(argv[0], line)
        print(message, file=sys.stderr, flush=True)
        return code


def _must(argv: list[str], line: int, **kw) -> None:
    """A bare command under `set -e`: any non-zero status ends the script.

    The status PROPAGATES; it is not flattened to 1. That distinction is the difference between a caller learning `node` exited 3 and a caller learning only that something went wrong, and it is a defect class this campaign has found in several other scripts. This one gets it right, so the port does too.

    `line` is the TWIN's line number, passed in rather than derived, because the only reader it serves is someone diffing this against `bash -x` output of the twin -- and a number derived from this file would point at the wrong script.
    """
    code = _status(argv, line, **kw)
    if code != 0:
        raise Refusal(code)


def _jq(doctor_output: str, program: str) -> str:
    """`echo "$X" | jq -r '<program>'`, trailing newlines stripped.

    `jq` is REAL on both sides. It is deterministic, it is the thing under test in these four lines, and a fake would only prove the fake agrees with itself.
    """
    proc = subprocess.run(
        ["jq", "-r", program],
        input=doctor_output + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stderr:
        sys.stderr.write(proc.stderr)
        sys.stderr.flush()
    return proc.stdout.rstrip("\n")


def _resolve_version() -> None:
    """`:124-137`. The version seam, and the only branch on `$RELEASE_BUILD`.

    THE SEAM IS THE RELEASE PATH, not "CI" -- the twin says so at length and the sentence is worth keeping next to the code: `ci-build-cli.yml` sets
    `RELEASE_BUILD=true` only on push-to-main, the one CI whose artifacts CD
    promotes, and there `--strict` refuses an empty, placeholder or malformed version before a single byte is stamped. PR CI, forks and local `./rdc.sh --native` leave it unset and keep the `0.0.0-dev` fallback.

    `inject()` returns the exports rather than performing them, and on EVERY refusal path it returns an empty dict -- matching the twin, whose sourced
    function `return`s before reaching its `export` statements, so a failed
    source leaves the caller's `CLI_VERSION` at its previous value.
    """
    if os.environ.get("RELEASE_BUILD", "") == TRUE:
        cli_version = os.environ.get("CLI_VERSION", "")
        if not cli_version:
            raise Refusal(
                1,
                "RELEASE_BUILD=true but CLI_VERSION is empty; "
                "refusing to build a publishable artifact without a version",
            )
        code, exports, out, err = inject_env.inject(["--version", cli_version, "--strict"])
        _emit(out, err)
        if code != 0:
            raise Refusal(
                1,
                "Release build refused: CLI_VERSION='%s' is not a publishable version"
                % cli_version,
            )
    else:
        code, exports, out, err = inject_env.inject(
            ["--version", os.environ.get("CLI_VERSION", "") or DEV_VERSION]
        )
        _emit(out, err)
        if code != 0:
            # A bare `source` under `set -e`. Unreachable today -- the argument is never empty -- but flattening it to a message the twin does not print would be inventing behaviour.
            raise Refusal(code)
    os.environ.update(exports)


def _emit(out: list[str], err: list[str]) -> None:
    """inject-env's own streams, in the twin's order: stderr first, then stdout."""
    for line in err:
        print(line, file=sys.stderr, flush=True)
    for line in out:
        print(line, flush=True)


def _smoke_tests(binary: str, expected_version: str) -> None:
    """`:246-339`. Two tests, run only on a NATIVE build.

    Test 1 is `--version` and is judged solely by its exit status (DEFECT 4). Test 2 is `doctor --output json`, whose stdout is captured and whose stderr is discarded (`2>/dev/null`), then put through four separate `jq` reads.
    """
    log.step("Running smoke test: --version")
    code = _status([binary, "--version"], 248)
    if code == 0:
        log.info("Smoke test (--version) passed")
    else:
        # `$?` here is the CONDITION's status: bash expands the arguments of the first command in the `else` branch before running it, so the value is still the one the `if` tested. Correct in the twin, and easy to get wrong in either direction.
        raise Refusal(1, "Smoke test (--version) failed (exit code: %d)" % code)

    log.step("Running smoke test: doctor --output json")
    doctor_output, doctor_exit = _doctor(binary)

    if doctor_exit <= DOCTOR_MAX_OK_EXIT and doctor_output:
        log.info("Doctor exited with code %d (expected in CI without auth/renet)" % doctor_exit)
        _check_doctor_json(doctor_output, expected_version)
        log.info("Smoke test (doctor) passed")
        return

    # THIS BRANCH IS WHERE A SIGNAL LANDS, and the twin says so: the success arm gates on `-le 2`, so 137 and 143 fall through to here and would otherwise be reported as a doctor VERDICT rather than as a kill.
    if SIGNAL_EXIT_LOW < doctor_exit < SIGNAL_EXIT_HIGH:
        line = "Doctor was KILLED by signal %d (raw %d), so it reported no verdict" % (
            doctor_exit - SIGNAL_EXIT_LOW,
            doctor_exit,
        )
    else:
        line = "Doctor command failed unexpectedly (exit code: %d)" % doctor_exit
    log.error(line)
    if doctor_output:
        print(doctor_output, flush=True)
    raise Refusal(1)


def _doctor(binary: str) -> tuple[str, int]:
    """`:259`. `$(... 2>/dev/null) || DOCTOR_EXIT=$?`, with stderr thrown away.

    The `||` is what keeps `set -e` off this call: a doctor that exits non-zero is the EXPECTED case in CI, and the status is data here rather than a fault.
    """
    try:
        proc = subprocess.run(
            [binary, "doctor", "--output", "json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        message, code = _exec_failure(binary, 259)
        print(message, file=sys.stderr, flush=True)
        return "", code
    text = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    return text.rstrip("\n"), proc.returncode


def _check_doctor_json(doctor_output: str, expected_version: str) -> None:
    """`:265-322`. Validate the JSON, then four separate assertions over it."""
    valid = subprocess.run(
        ["jq", "empty"],
        input=doctor_output + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if valid.returncode != 0:
        log.error("Doctor output is not valid JSON")
        print(doctor_output, flush=True)
        raise Refusal(1)
    log.info("Doctor JSON output is valid")

    install_method = _jq(
        doctor_output, '.Environment[] | select(.name == "Install method") | .value'
    )
    reported_version = _jq(
        doctor_output, '.Environment[] | select(.name == "CLI version") | .value'
    )
    node_status = _jq(doctor_output, '.Environment[] | select(.name == "Node.js") | .status')

    if install_method == EXPECTED_INSTALL_METHOD:
        log.info("Install method: %s" % install_method)
    else:
        raise Refusal(1, "SEA mode check failed: '%s'" % install_method)

    # THE ONLY POINT IN THE WHOLE PIPELINE THAT READS A VERSION OUT OF FRESHLY
    # BUILT BYTES, and the twin's comment records why it is a comparison rather than a non-empty test: release 31154305287 published binaries built as 1.2.16 under the label 1.2.17, and this step said "CLI version: 1.2.16" and passed. `EXPECTED_CLI_VERSION` exists as a separate variable in the twin for the same reason -- `$CLI_VERSION` used to be clobbered by the jq read below it,
    # leaving nothing to compare against.
    if not reported_version or reported_version == "null":
        raise Refusal(1, "CLI version check failed: doctor reported '%s'" % reported_version)
    if reported_version != expected_version:
        raise Refusal(
            1,
            "CLI version mismatch: built for '%s' but the binary reports '%s'"
            % (expected_version, reported_version),
        )
    log.info("CLI version: %s (matches build version)" % reported_version)

    if node_status == EXPECTED_NODE_STATUS:
        log.info("Node.js status: %s" % node_status)
    else:
        raise Refusal(1, "Node.js check failed: status='%s'" % node_status)

    # Runtime embedded-asset integrity. `doctor` reads the host renet binary back out of the SEA and sha256-checks it against the build-time metadata: the ONE runtime check a corrupt or unreachable blob cannot pass. `--version` never touches an asset, and `verify.mjs` only parses the container without running it, so without this a blob whose main script is intact and whose payload
    # is shredded ships green.
    embed_corrupt = _jq(
        doctor_output,
        '[.Renet[]? | select(.value | startswith("%s"))] | length' % CORRUPT_PREFIX,
    )
    if embed_corrupt == "0":
        log.info("Embedded renet asset read back and sha256-verified")
    else:
        log.error("Embedded renet asset integrity check FAILED (corrupt/unreachable blob)")
        detail = _jq(
            doctor_output,
            '.Renet[]? | select(.value | startswith("%s")) | "  \\(.name): \\(.value)"'
            % CORRUPT_PREFIX,
        )
        print(detail, flush=True)
        raise Refusal(1)


def _checksum(output_dir: str, name: str) -> None:
    """`:230-240`, DEFECT 3 included.

    Both tools are run from INSIDE the output directory with a bare filename, so the `.sha256` file records `<hash> rdc-linux-x64` and not a path -- which is what `sha256sum -c` in the release job later expects to find.
    """
    log.step("Generating SHA256 checksum...")
    target = pathlib.Path(output_dir) / ("%s.sha256" % name)
    if shutil.which("sha256sum") is not None:
        with target.open("wb") as handle:
            _must(["sha256sum", name], 232, cwd=output_dir, stdout=handle)
    elif shutil.which("shasum") is not None:
        with target.open("wb") as handle:
            _must(["shasum", "-a", "256", name], 234, cwd=output_dir, stdout=handle)
    else:
        # DEFECT 3. A warning, and the build carries on to publish a binary with nothing to verify it against.
        log.warn("No sha256sum or shasum available - skipping checksum")
    if target.is_file():
        log.info("Checksum: %s" % target.read_text(encoding="utf-8").rstrip("\n"))


def build(argv: list[str]) -> int:
    """The twin, top to bottom, in its order. Deliberately not decomposed.

    A helper per phase would read better and would make the ORDER -- which is the thing a differential compares -- a property of five call sites instead of one readable sequence. The twin is a 344-line straight line; so is this.
    """
    # `:21`, before anything else. Two `uname` processes and three exported variables, paid by every sourcer of common.sh; see `source_common`.
    source_common()

    platform_name, arch, output_dir, dry_run, help_line = parse_args(argv)
    if help_line is not None:
        print(
            "Usage: %s [--platform PLATFORM] [--arch ARCH] [--output DIR] [--dry-run]"
            % sys.argv[0],
            flush=True,
        )
        return 0

    # `:60-71`. Auto-detect only when the flag was omitted. The error arm calls `uname` a SECOND time to build its message, and the count is observable.
    if not platform_name:
        system = uname("-s")
        detected = platform_from_uname(system)
        if detected is None:
            raise Refusal(1, "Cannot detect platform from: %s" % uname("-s"))
        platform_name = detected
        log.info("Auto-detected platform: %s" % platform_name)

    if not arch:
        machine = uname("-m")
        detected_arch = arch_from_uname(machine)
        if detected_arch is None:
            raise Refusal(1, "Cannot detect architecture from: %s" % uname("-m"))
        arch = detected_arch
        log.info("Auto-detected arch: %s" % arch)

    root = console_root()
    sdir = script_dir(root)
    if not output_dir:
        output_dir = str(root / "dist" / "cli")

    name = binary_name(platform_name, arch)
    cli_dir = root / "packages" / "cli"

    # `:99`. DEFECT 1: a silent exit 1, before anything has been printed.
    node = node_bin()
    if node is None:
        return 1

    log.step("Building CLI SEA executable: %s" % name)
    log.info("  Platform: %s" % platform_name)
    log.info("  Arch: %s" % arch)
    log.info("  Node: %s (%s)" % (node, _capture(["node", "--version"])))
    log.info("  Output: %s/%s" % (output_dir, name))

    if dry_run:
        log.info("[DRY-RUN] Would build %s" % name)
        return 0

    # STEP 1: the CJS bundle.
    log.step("Building CLI bundle...")
    _resolve_version()
    # The version this build was TOLD to produce, kept separate because the doctor smoke test parses a value into `CLI_VERSION` and used to clobber it.
    expected_cli_version = os.environ.get("CLI_VERSION", "")
    log.info("CLI version: %s" % expected_cli_version)

    try:
        os.chdir(cli_dir)
    except OSError as exc:
        # The `cd` divergence; see the module head. The tail after the masked prefix is bash's own wording.
        print(
            "%s: line %d: cd: %s: %s"
            % (sys.argv[0], sys._getframe().f_lineno, cli_dir, exc.strerror),
            file=sys.stderr,
            flush=True,
        )
        return 1

    _must(["node", "bundle.mjs"], 144)
    require_file(str(cli_dir / "dist" / "cli-bundle.cjs"))
    log.info("Bundle created: %d bytes" % _size("dist/cli-bundle.cjs"))

    # STEP 1.5: embedded renet assets, via the BASH sibling (see the module head).
    log.step("Preparing embedded renet assets...")
    _must([str(sdir / "prepare-cli-assets.sh"), "--platform", platform_name, "--arch", arch], 150)

    # STEP 2: the SEA blob.
    log.step("Generating SEA blob...")
    _must(["node", "--experimental-sea-config", "sea-config.generated.json"], 154)
    require_file(str(cli_dir / "dist" / "sea-prep.blob"))
    log.info("SEA blob created: %d bytes" % _size("dist/sea-prep.blob"))

    # STEP 3: the host node binary becomes the artifact.
    log.step("Copying node binary...")
    target = "%s/%s" % (output_dir, name)
    pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
    _must(["cp", node, target], 161)
    _must(["chmod", "+x", target], 162)

    # STEP 4: macOS only, and it MUST precede the strip.
    if platform_name == "mac":
        log.step("Removing existing code signature...")
        _must(["codesign", "--remove-signature", target], 167)

    # STEP 5: strip before injection, so the SEA section cannot be corrupted by it. macOS `strip` is incompatible with node binaries (__LINKEDIT), so only Linux strips. DEFECT 2 lives on this line.
    if platform_name == "linux":
        log.step("Stripping debug symbols...")
        _must(["strip", "--strip-all", target], 175)
        log.info("Stripped binary: %d bytes" % _size(target))

    # STEP 6: injection, with OUR streaming injector on EVERY platform rather than `npx postject` (#525). postject is LIEF compiled to wasm32, so the executable and the blob must both fit a 4GB address space, and it amplifies the blob ~11.6x in memory: a ~561MB blob needs ~7.4GB and cannot be injected at all. Upstream's last release is 2023-05 and its wasm memory is already at the
    # architectural maximum, so it is not fixable there. sea-inject/ streams in fixed-size chunks, flat ~64MB RSS regardless of blob size, with ELF / Mach-O / PE backends dispatched by magic bytes.
    log.step("Injecting SEA blob into binary...")
    inject_args = [
        target,
        BLOB_NAME,
        str(cli_dir / "dist" / "sea-prep.blob"),
        "--sentinel-fuse",
        SENTINEL_FUSE,
    ]
    if platform_name == "mac":
        inject_args += ["--macho-segment-name", MACHO_SEGMENT_NAME]
    _must(["node", str(sdir / "sea-inject" / "cli.mjs"), *inject_args], 203)

    # STEP 7: the integrity gate. Re-extract the embedded blob and SHA256-compare it to the source, on EVERY platform: this only PARSES the container, it does not execute it, so it runs for cross-compiled mac/win/arm64 too. It is the check that catches a corrupt or truncated injection before release, because the native-only smoke tests below exercise the SEA main script but not the
    # asset bytes (#525).
    log.step("Verifying embedded SEA blob integrity...")
    _must(
        [
            "node",
            str(sdir / "sea-inject" / "verify.mjs"),
            target,
            str(cli_dir / "dist" / "sea-prep.blob"),
            "--sentinel-fuse",
            SENTINEL_FUSE,
        ],
        213,
    )

    # STEP 8: macOS re-sign, ad-hoc.
    if platform_name == "mac":
        log.step("Re-signing binary...")
        _must(["codesign", "-s", "-", target], 221)

    log.step("Verifying executable...")
    binary_size = _size(target)
    log.info("Binary size: %dMB (%d bytes)" % (binary_size // 1024 // 1024, binary_size))

    _checksum(output_dir, name)

    # `:243-244`. NATIVE builds only. The `&&` SHORT-CIRCUITS, so `detect_arch` (and its `uname -m`) does not run when the platform already disagrees -- observable in a call log, which is why this is an `and` over two calls and not a precomputed tuple.
    if platform_name == native_platform_name() and arch == detect_arch():
        _smoke_tests(target, expected_cli_version)
    else:
        log.info("Skipping smoke tests (cross-platform build)")

    log.info("CLI SEA build complete: %s/%s" % (output_dir, name))
    return 0


def main(argv: list[str]) -> int:
    try:
        return build(argv)
    except Refusal as refusal:
        for line in refusal.lines:
            if refusal.raw:
                print(line, file=sys.stderr, flush=True)
            else:
                log.error(line)
        return refusal.code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
