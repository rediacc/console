#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-linux-pkg.sh`.

Builds exactly ONE Linux package -- one (format, arch) pair -- from an already
built CLI binary, using nfpm. It replaced the old `build-deb.sh` (dpkg-deb) and
`build-rpm.sh` (rpmbuild) with a single nfpm-driven builder that also covers apk
(Alpine) and archlinux (pacman).

Its only caller is `build-linux-packages.sh`, which fans out eight invocations
(four formats x two arches); that fan-out is already ported at
`build/build_linux_packages.py`, and its docstring records why it does NOT
reimplement this file. This is the other half of that pair.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT:

  * `nfpm package`, the whole point of the script.
  * `gpg --show-keys --with-colons --with-fingerprint`, twice, once per key. The
    FINGERPRINT COMPARISON is the check that stops a package being signed with a
    key no client trusts, and a Python OpenPGP parser here would be a second
    implementation of what gpg already answers.
  * `.ci/scripts/build/canonicalise-gpg-key.sh`, the BASH sibling, by the path
    the twin builds. Its exit code 10 means "the stored armor was malformed and
    I repaired it in flight", and it is shared precisely so
    `check:ci-release-key-canonical` exercises the real thing; calling a Python
    reimplementation would make that gate certify a different instrument.
  * `find`, for nfpm's output. Not `Path.glob`: `find -maxdepth 1` returns
    DIRECTORY ORDER and `head -1` takes whatever came first, so a sorted Python
    glob would pick a different file whenever nfpm emits more than one. That
    only bites in a case the twin also handles badly, and imitating the badly is
    the job.
  * `mkdir -p`, at BOTH sites (`:148` and `:266`). Not `Path.mkdir`: the twin
    runs the real `mkdir` under `set -e`, so an output directory with a FILE in
    its path prints `mkdir: ...` and exits 1, where `Path.mkdir` raises a Python
    traceback. Driven, not reasoned about: `mkdir -p "$d/f"` over a regular file
    exits 1 with `mkdir: Already exists` on this machine's coreutils, and
    shelling out is the only way to get that byte-identical rather than
    approximated.
  * `uname -s` / `uname -m`, twice, because sourcing `common.sh` costs them; see
    `source_common`.

NOT SHELLED OUT:

  * `mktemp -d` -> `tempfile.mkdtemp()`, and `trap cleanup EXIT` -> a `finally`.
  * `echo "$KEY" >"$file"` -> `_bash_echo`, which is a file write with one
    trailing newline in every case but one. bash's BUILTIN `echo` parses a
    leading `-n`/`-e`/`-E` as OPTIONS, so a key whose entire value is `-n`
    writes a ZERO-BYTE file; `-----BEGIN...` is not a valid option string and is
    printed literally, which is why real armor is unaffected. Reproduced rather
    than smoothed over, because the empty file it produces then walks straight
    into DEFECT 2.
  * `wc -c` -> `stat().st_size`; `tr '[:upper:]' '[:lower:]'` -> `str.lower()`;
    `${FORMAT^^}` -> `str.upper()`; `basename`/`dirname` -> `os.path`.
  * `.ci/config/constants.sh`. It is a bash file with `readonly` declarations and
    a hard dependency on `.devcontainer/toolchain.env`; sourcing it from Python
    means running bash to print an environment, which is a third way to spell the
    same seven strings. They are RESTATED below, the way
    `docker/cleanup_staging.py` and `docker/create_manifest.py` restate theirs,
    and `test_build_linux_pkg.py::test_the_restated_constants_match_constants_sh`
    parses the real file and fails on drift. A stale constant here is a
    mislabelled package, so the alarm is not optional.

-----------------------------------------------------------------------------
SIX REAL DEFECTS IN THE TWIN, REPRODUCED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
DEFECT 1 -- THE FINGERPRINT CHECK IS SKIPPED WHOLESALE WHEN THE PUBLISHED KEY
FILE IS ABSENT. `:225` is `if [[ -f "$PUBLIC_KEY_FILE" ]]; then ... fi` with no
`else`. Point `RELEASE_GPG_PUBLIC_KEY_FILE` at a path that does not exist, or
build in a checkout without `.ci/keys/gpg-public.asc`, and the entire "is this
the key clients trust" comparison silently does not happen -- while the code
above it has already announced "Setting up GPG signing". The check that cannot
run is folded into the check that passed, which is the exact class this campaign
keeps finding. Reproduced.

DEFECT 2 -- AND WHEN THE KEY FILE IS PRESENT BUT UNREADABLE, THE SCRIPT DIES
SILENTLY INSTEAD OF SAYING SO. `:226` is

    want_fpr=$(gpg --show-keys ... "$PUBLIC_KEY_FILE" 2>/dev/null | awk ...)

An assignment whose right-hand side is a PIPELINE, under `set -o pipefail`. gpg
exits 2 on a file that is not a key, awk exits 0, pipefail makes the pipeline 2,
and `set -e` kills the script before the next line runs. Driven on bash 5.3.9:
`x=$( (exit 2) | awk '{print}' )` exits 2 with nothing on either stream. The
consequence is that `${want_fpr:-<unreadable>}` on `:229` -- a fallback written
specifically for this case -- is DEAD CODE and can never print. The build fails
with a bare exit 2 and no diagnosis at all. Reproduced, including the status.

DEFECT 3 -- `find | head -1` UNDER pipefail IS A SILENT DEATH, AND IT IS LIVE,
NOT LATENT. `:277-279` has the same assignment-of-a-pipeline shape as DEFECT 2.
`find` exits 1 whenever it cannot read something it was asked to walk, and
`head` exits 0, so pipefail hands the assignment a 1 and `set -e` ends the build
with NOTHING but find's own `Permission denied` on stderr -- no `log_error`, no
"nfpm produced no output file", no diagnosis. Driven on bash 5.3.9 against a
`chmod 000` subdirectory: exit 1, and the only line printed is find's.
REPRODUCED, status included; `test_defect_3_a_failing_find_dies_silently`
drives it. A SECOND arm of the same defect stays latent and is recorded rather
than driven: with enough output to fill the 64KB pipe buffer `find` takes
SIGPIPE (141) instead, which needs hundreds of package files in one temp
directory to trigger.

DEFECT 4 -- THE POST-COPY EXISTENCE CHECK IS UNREACHABLE. `:291-294` tests
`[[ ! -f "$OUTPUT_DIR/$PKG_FILE" ]]` immediately after an unguarded `cp` under
`set -e`. A `cp` that failed already ended the script, so "Package build failed:
X not found" cannot be printed. Carried as-is; the port keeps the branch so a
reader diffing the two files does not think it was dropped.

DEFECT 5 -- `--dry-run` VALIDATES NOTHING. `:146-150` exits 0 after creating the
output directory, BEFORE `require_file "$BINARY"` and BEFORE `require_cmd nfpm`.
The twin's own comment says this is deliberate ("not needed for validation-only
runs"), which makes it a documented decision rather than an accident, but the
consequence stands: a preview cannot tell you the binary is missing, and a
preview path that runs ahead of validation is the shape this campaign checks
for. Reproduced with the comment intact.

DEFECT 6 -- "SIGNED" MEANS "A KEY WAS CONFIGURED", NOT "A SIGNATURE EXISTS".
`SIGNING_CONFIGURED` is set to true by the presence of a key, and `:300` then
reports "Package signed with DEB key" without ever asking nfpm whether it signed
anything. For apk it also says "APK key" for what is an RSA key, not a GPG one.
Reproduced.

NOT A DEFECT, AND WORTH SAYING SO: the empty-secret guard at `:310`. An org
secret deleted on 2026-09-05 made `${{ secrets.X }}` resolve to `""`, which was
indistinguishable from "no signing wanted", and the build shipped an UNSIGNED
package green. `RELEASE_SIGNING_REQUIRED=1` now turns that silence into a hard
failure. apk and archlinux are DECLARED-UNSIGNED (no key exists for apk;
nfpm cannot sign archlinux at all, goreleaser/nfpm#628) and each says so out
loud rather than finishing in silence.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE
-----------------------------------------------------------------------------
`RELEASE_GPG_PRIVATE_KEY`, `RELEASE_GPG_PASSPHRASE`,
`RELEASE_GPG_PUBLIC_KEY_FILE`, `APK_RSA_PRIVATE_KEY` and
`RELEASE_SIGNING_REQUIRED` are each read with a direct
`os.environ.get("NAME", "")` where they are used. No dict alias, no loop: the
env-manifest reader parses direct reads by name and an alias hides them, which
this campaign has confirmed in four separate waves.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log

# ---------------------------------------------------------------------------
# `.ci/config/constants.sh:206-212`, RESTATED. See the module head for why, and
# `test_the_restated_constants_match_constants_sh` for the alarm that keeps them
# honest. Each is a bare `readonly NAME="value"` in the twin -- no `${NAME:-...}`
# -- so the environment CANNOT override any of them, and a caller that exports
# `PKG_NAME` has it overwritten by the source. That is why these are constants
# here and not `os.environ.get` calls.
# ---------------------------------------------------------------------------
PKG_NAME = "rediacc-cli"
PKG_BINARY_NAME = "rdc"
PKG_MAINTAINER = "Rediacc <info@rediacc.com>"
PKG_DESCRIPTION = "Rediacc CLI - automation and scripting tool"
PKG_HOMEPAGE = "https://www.rediacc.com"
PKG_SECTION = "utils"
PKG_PRIORITY = "optional"

# `:83-89`. The four nfpm packagers, in the twin's `case` order.
FORMATS = ("deb", "rpm", "apk", "archlinux")

# `:96-113`. nfpm speaks GOARCH; the other three names appear only in filenames.
# Keyed by every spelling the twin accepts, so an unknown key is the refusal.
ARCH_MAP = {
    "amd64": ("amd64", "x86_64", "x86_64", "amd64"),
    "x86_64": ("amd64", "x86_64", "x86_64", "amd64"),
    "arm64": ("arm64", "aarch64", "aarch64", "arm64"),
    "aarch64": ("arm64", "aarch64", "aarch64", "arm64"),
}

# `:198`. The sibling that repairs a welded GPG armor. Exit 10 is "repaired", and
# it is a SIGNAL rather than a failure: a bare call under `set -e` aborted every
# build whose key needed repairing, which is exactly the production case the
# signal exists for.
CANON_REPAIRED = 10

# `:224`. The published public key, and its environment override.
DEFAULT_PUBLIC_KEY_REL = ".ci/keys/gpg-public.asc"

# `:264`. nfpm's config, which is a template over the exported variables below.
NFPM_CONFIG_REL = ".ci/config/nfpm.yaml"

# `:310`. The literal the caller sets to say "an unsigned artifact is a failure".
SIGNING_REQUIRED_ON = "1"

# `:277-278`. What nfpm might have written, as `find -name` patterns.
PACKAGE_GLOBS = ("*.deb", "*.rpm", "*.apk", "*.pkg.tar.zst")

# `:187` and `:254`. bash's BUILTIN `echo` consumes a leading argument made only
# of `n`, `e` and `E` after a single dash as OPTIONS rather than printing it.
BASH_ECHO_OPTION = re.compile(r"-[neE]+\Z")


class Refusal(Exception):  # noqa: N818 - named for what the twin does
    """A `log_error ...; exit N`, or a bare `set -e` death when `lines` is empty.

    DEFECT 2 is the reason the empty case exists: the twin genuinely exits
    non-zero having printed nothing, and a port that invented a message there
    would be describing a better program than the one that runs.
    """

    def __init__(self, code: int, *lines: str) -> None:
        super().__init__(lines[0] if lines else "")
        self.code = code
        self.lines = lines


def console_root() -> pathlib.Path:
    """`get_repo_root` (`common.sh:205-210`), which has no environment override.

    `rediacc_ci.paths.repo_root()` honours `$REDIACC_CI_ROOT` and is deliberately
    not used: a differential where one side follows an override and the other
    does not diverges for a reason that says nothing about the port. Same
    derivation as `build_linux_packages.py` and `build_cli_executables.py`.
    """
    # This file: <root>/.ci/rediacc_ci/build/build_linux_pkg.py
    return pathlib.Path(__file__).resolve().parents[3]


def script_dir(root: pathlib.Path) -> pathlib.Path:
    """`$(dirname "${BASH_SOURCE[0]}")` at `:198` -- where the BASH twin lives.

    Note that `:198` uses this rather than `$SCRIPT_DIR` from `:24`, so the
    twin's canonicaliser path is RELATIVE when the twin itself was invoked by a
    relative path and absolute otherwise. The two forms name the same file; this
    port always produces the absolute one, which is what `$SCRIPT_DIR` would have
    given had `:198` used it.
    """
    return root / ".ci" / "scripts" / "build"


def source_common() -> None:
    """`common.sh:504-514` -- two `uname` processes and three exported variables.

    Not a function in the twin: sourcing the library RUNS it, so every child this
    script spawns (nfpm, gpg, the canonicaliser) inherits `CI_OS`, `CI_ARCH` and
    `CI_TEMP`. A port that skipped it would hand nfpm a different environment.
    Duplicated in this wave's other two ports on purpose; see
    `build_cli_executables.source_common` for the note on lifting it.
    """
    os.environ["CI_OS"] = _detect_os()
    os.environ["CI_ARCH"] = _detect_arch()
    os.environ["CI_TEMP"] = (
        os.environ.get("RUNNER_TEMP", "") or os.environ.get("TMPDIR", "") or "/tmp"
    )


def _bash_echo(value: str) -> str:
    """What `echo "$VALUE"` WRITES, which is not always `VALUE` plus a newline.

    bash's builtin `echo` parses `-n`, `-e`, `-E` and any combination of those
    letters as OPTIONS. A `RELEASE_GPG_PRIVATE_KEY` whose entire value is `-n`
    therefore produces a ZERO-BYTE key file, and the build then walks into
    DEFECT 2 with no idea why. Driven: `v=-n; echo "$v" >f` leaves `wc -c` = 0.

    Real armor is safe -- `-----BEGIN PGP PRIVATE KEY BLOCK-----` contains
    characters other than n/e/E, so it is not an option string and is printed
    literally -- and that is exactly why this is worth spelling out rather than
    assuming the leading dashes make it a general hazard.

    Escapes are NOT interpreted: that needs `-e` or `shopt -s xpg_echo`, and the
    twin uses neither at these two call sites. (`log_*` DOES use `echo -e`; see
    the note on `rediacc_ci.log` in `test_build_linux_pkg.py`.)
    """
    if BASH_ECHO_OPTION.fullmatch(value):
        return "" if "n" in value else "\n"
    return value + "\n"


def _capture(argv: list[str]) -> str:
    """`$(cmd)` -- stdout with trailing newlines stripped, stderr inherited.

    The STATUS IS DISCARDED, which is right only where the twin discards it too:
    `case "$(uname -s)" in` is a case WORD, not a simple command, so `set -e`
    never sees it and `detect_os` fails open to `unknown`. Anywhere the twin
    assigns a command substitution to a variable the status is load-bearing and
    this function is the wrong tool; see `_capture_or_die`.
    """
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, check=False)
    except OSError:
        return ""
    return proc.stdout.decode("utf-8", errors="replace").rstrip("\n") if proc.stdout else ""


def _capture_or_die(argv: list[str]) -> str:
    """`VAR=$(cmd | ...)` -- the assignment form, whose status `set -e` DOES see.

    DEFECT 3 lives here, and it is the same shape as DEFECT 2 one function up: a
    non-zero status ends the script with no message of its own. `head -1` cannot
    contribute a status because it exits 0, so the left-hand command's is the
    only one `pipefail` can propagate.
    """
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, check=False)
    except OSError:
        message, code = _exec_failure(argv[0], 277)
        print(message, file=sys.stderr, flush=True)
        raise Refusal(code) from None
    if proc.returncode != 0:
        raise Refusal(proc.returncode)
    return proc.stdout.decode("utf-8", errors="replace").rstrip("\n") if proc.stdout else ""


def _detect_os() -> str:
    """`common.sh:63-72`, including the fail-open `unknown` arm."""
    system = _capture(["uname", "-s"])
    if system.startswith("Linux"):
        return "linux"
    if system.startswith("Darwin"):
        return "macos"
    if system.startswith(("CYGWIN", "MINGW", "MSYS")):
        return "windows"
    return "unknown"


def _detect_arch() -> str:
    """`common.sh:98-106`, same fail-open default."""
    machine = _capture(["uname", "-m"])
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    return "unknown"


def parse_args(argv: list[str]) -> tuple[dict[str, str], bool, bool]:
    """`:37-72`. Returns `(values, dry_run, wants_help)`.

    A flag whose value is missing is a `set -u` death in the SHELL, not a refusal
    this function can express; `main()` reproduces it with the twin's own line
    numbers. The `*)` arm is present, which is the thing to check for.
    """
    values = {"BINARY": "", "VERSION": "", "ARCH": "", "FORMAT": "", "OUTPUT": ""}
    lines = {"BINARY": 40, "VERSION": 44, "ARCH": 48, "FORMAT": 52, "OUTPUT": 56}
    flags = {
        "--binary": "BINARY",
        "--version": "VERSION",
        "--arch": "ARCH",
        "--format": "FORMAT",
        "--output": "OUTPUT",
    }
    dry_run = False
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        if flag in flags:
            key = flags[flag]
            if not rest:
                raise Refusal(1, "%s: line %d: $2: unbound variable" % (sys.argv[0], lines[key]))
            values[key] = rest.pop(0)
        elif flag == "--dry-run":
            dry_run = True
        elif flag in ("-h", "--help"):
            return values, dry_run, True
        else:
            raise Refusal(1, "✗ Unknown option: %s" % flag)
    return values, dry_run, False


def package_filename(fmt: str, version: str, arch_names: tuple[str, str, str, str]) -> str:
    """`:119-132`. Four naming conventions, kept for backwards compatibility.

    Exported so the four spellings can be asserted without a build. `arch_names`
    is `(nfpm, rpm, archlinux, deb)`, the tuple `ARCH_MAP` stores, in that order.
    """
    nfpm_arch, rpm_arch, archlinux_arch, deb_arch = arch_names
    if fmt == "deb":
        return "%s_%s_%s.deb" % (PKG_NAME, version, deb_arch)
    if fmt == "rpm":
        return "%s-%s-1.%s.rpm" % (PKG_NAME, version, rpm_arch)
    if fmt == "apk":
        return "%s-%s-r1-%s.apk" % (PKG_NAME, version, nfpm_arch)
    return "%s-%s-1-%s.pkg.tar.zst" % (PKG_NAME, version, archlinux_arch)


def require_file(path: str) -> None:
    """`common.sh:151-157`, verbatim."""
    if not pathlib.Path(path).is_file():
        raise Refusal(1, "✗ Required file '%s' does not exist" % path)


def require_cmd(cmd: str) -> None:
    """`common.sh:141-147`, verbatim. Only the FIRST argument is validated in the
    twin, and a second "label" argument some callers pass is silently discarded;
    this script passes one argument at both call sites, so the quirk is latent
    here and is not reproduced as an interface."""
    if shutil.which(cmd) is None:
        raise Refusal(1, "✗ Required command '%s' is not available" % cmd)


def fingerprint(key_file: str) -> str:
    """`:226-227`. The first `fpr` row's field 10, or a silent death.

    DEFECT 2 LIVES HERE AND IT IS THE WHOLE REASON THIS IS A FUNCTION. The twin
    writes the gpg call as the right-hand side of an assignment, which makes the
    PIPELINE's status the assignment's status; under `pipefail` a gpg that exits
    2 kills the script with no output, so the `<unreadable>` fallback two lines
    later can never be reached. `awk -F: '$1=="fpr"{print $10; exit}'` always
    exits 0, so gpg's status is the only one that can be non-zero.

    The awk program itself is reimplemented (split on `:`, first row whose field
    1 is `fpr`, take field 10) because it is four tokens of text processing, not
    a tool whose behaviour is under test.
    """
    proc = subprocess.run(
        ["gpg", "--show-keys", "--with-colons", "--with-fingerprint", key_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode != 0:
        # DEFECT 2: `set -e` on the pipeline's status, no message, gpg's code.
        raise Refusal(proc.returncode)
    for line in proc.stdout.decode("utf-8", errors="replace").split("\n"):
        fields = line.split(":")
        if fields and fields[0] == "fpr":
            return fields[9] if len(fields) > 9 else ""
    return ""


def _run(argv: list[str], line: int, **kw) -> None:
    """A bare command under `set -e`. The status PROPAGATES, unflattened."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        code = subprocess.run(argv, check=False, **kw).returncode
    except OSError:
        message, code = _exec_failure(argv[0], line)
        print(message, file=sys.stderr, flush=True)
    if code != 0:
        raise Refusal(code)


def _exec_failure(command: str, line: int) -> tuple[str, int]:
    """bash's own two diagnostics; see `build_cli_executables._exec_failure`."""
    if "/" in command:
        if pathlib.Path(command).exists():
            return "%s: line %d: %s: Permission denied" % (sys.argv[0], line, command), 126
        return "%s: line %d: %s: No such file or directory" % (sys.argv[0], line, command), 127
    return "%s: line %d: %s: command not found" % (sys.argv[0], line, command), 127


def _setup_gpg_signing(fmt: str, build_dir: str, root: pathlib.Path) -> None:
    """`:182-249`. The rpm/deb arm: write the key, canonicalise it, prove it is
    the PUBLISHED key, then hand nfpm the file through its own env vars."""
    log.info("Setting up GPG signing for %s..." % fmt)

    key_file = os.path.join(build_dir, "signing-key.gpg")
    with open(key_file, "w", encoding="utf-8") as handle:
        handle.write(_bash_echo(os.environ.get("RELEASE_GPG_PRIVATE_KEY", "")))

    # CANONICALISE THE ARMOR BEFORE nfpm SEES IT. gpg parses leniently, nfpm's Go
    # decoder does not, and the failure lands AFTER the fingerprint check below
    # has printed a tick. `|| canon_rc=$?` in the twin rather than a bare call,
    # because exit 10 is a SIGNAL and a bare call under `set -e` aborted every
    # build whose key needed repairing.
    try:
        canon = subprocess.run(
            [
                str(script_dir(root) / "canonicalise-gpg-key.sh"),
                key_file,
                os.environ.get("RELEASE_GPG_PASSPHRASE", ""),
            ],
            check=False,
        )
        canon_rc = canon.returncode
    except OSError:
        # `|| canon_rc=$?` catches an exec failure too: bash prints its own
        # diagnostic and yields 126/127, and the script carries on to the `else`
        # arm below rather than dying.
        message, canon_rc = _exec_failure(str(script_dir(root) / "canonicalise-gpg-key.sh"), 198)
        print(message, file=sys.stderr, flush=True)

    if canon_rc == 0:
        log.info("Signing key armor was already canonical")
    elif canon_rc == CANON_REPAIRED:
        # LOUD ON PURPOSE. Repairing this every build and saying nothing is how
        # the stored value stays broken forever. It is welded because a GPG key
        # does not fit one Bitwarden field and the two halves were joined
        # without a newline.
        log.warn(
            "SIGNING KEY WAS REPAIRED: the stored RELEASE_GPG_PRIVATE_KEY armor is "
            "malformed and this build fixed it in flight. Fix it AT SOURCE -- re-join "
            "the two Bitwarden halves WITH a newline -- or every build keeps papering "
            "over it."
        )
    else:
        # Not fatal on its own: the key may already be canonical, and the
        # fingerprint check below still has to pass. Said out loud rather than
        # proceeding silently, because the next failure would come from inside
        # nfpm.
        log.warn("could not canonicalise the signing key; handing nfpm the key as stored")

    # THE PACKAGE SIGNING KEY MUST BE THE PUBLISHED PUBLIC KEY. dnf verifies every
    # rpm against the gpg.key the repository publishes, so a package signed with
    # any other key installs nowhere and nothing here would have said so.
    # DECLARED, because the check below runs gpg inside a command substitution:
    # under `set -euo pipefail` a missing gpg exits 127 with no message, before
    # any log_error, so the signing check would silently not happen.
    require_cmd("gpg")
    public_key_file = os.environ.get("RELEASE_GPG_PUBLIC_KEY_FILE", "") or str(
        root / DEFAULT_PUBLIC_KEY_REL
    )
    if pathlib.Path(public_key_file).is_file():
        want_fpr = fingerprint(public_key_file)
        have_fpr = fingerprint(key_file)
        if not want_fpr or not have_fpr or want_fpr != have_fpr:
            raise Refusal(
                1,
                "✗ signing key %s is not the published public key %s (%s); a %s "
                "signed with it would fail verification on every client"
                % (
                    have_fpr or "<unreadable>",
                    want_fpr or "<unreadable>",
                    public_key_file,
                    fmt,
                ),
            )
        log.info("Signing key matches the published public key (%s)" % want_fpr)
    # DEFECT 1: no `else`. A missing published key means the comparison above
    # simply does not happen, and the build says nothing about having skipped it.

    # nfpm reads key_file from its YAML config, which references these env vars.
    if fmt == "rpm":
        os.environ["NFPM_RPM_KEY_FILE"] = key_file
    elif fmt == "deb":
        os.environ["NFPM_DEB_KEY_FILE"] = key_file

    passphrase = os.environ.get("RELEASE_GPG_PASSPHRASE", "")
    if passphrase:
        print("::add-mask::%s" % passphrase, flush=True)
        os.environ["NFPM_RPM_PASSPHRASE"] = passphrase
        os.environ["NFPM_DEB_PASSPHRASE"] = passphrase


def _report_unsigned(fmt: str) -> None:
    """`:302-344`. One arm per format, and every one of them SPEAKS.

    Silence is what let "two of four formats ship unsigned" go unnoticed, so
    archlinux -- which had no arm at all until it was added -- now says why it
    cannot be signed rather than finishing quietly.
    """
    if fmt in ("rpm", "deb"):
        # AN EMPTY KEY USED TO SHIP AN UNSIGNED PACKAGE, GREEN. The org secret
        # this used to read was deleted on 2026-09-05, so `${{ secrets.X }}`
        # resolved to "" -- indistinguishable here from "no signing wanted".
        if os.environ.get("RELEASE_SIGNING_REQUIRED", "0") == SIGNING_REQUIRED_ON:
            raise Refusal(
                1,
                "✗ RELEASE_SIGNING_REQUIRED=1 but RELEASE_GPG_PRIVATE_KEY is empty "
                "or unset -- refusing to ship an UNSIGNED %s. An empty value here means "
                "the secret resolved to nothing, not that signing was not wanted." % fmt,
            )
        log.warn("RELEASE_GPG_PRIVATE_KEY not set, skipping %s signing" % fmt)
    elif fmt == "apk":
        # NOT REQUIRED, and this is a correction. A class sweep made apk required
        # to match the GPG guard without checking that a key existed. It does
        # not: APK_RSA_PRIVATE_KEY is set by NOTHING in this repo and is absent
        # from bws-secret-map.json, so apk has never been signed, and the guard
        # blocked a release for a credential nobody has (run 34003316362, v1.3.9).
        log.warn(
            "APK_RSA_PRIVATE_KEY not set, skipping APK signing (apk is "
            "declared-unsigned; see check-release-signing-coverage.sh)"
        )
    else:
        # nfpm has no signature support for archlinux at all (goreleaser/nfpm#628
        # open, PR #1065 unmerged), and signing by hand would BREAK existing
        # users: pacman.conf(5) SigLevel Optional, which is what Arch ships as
        # LocalFileSigLevel, makes "a signature from a key not in the keyring" a
        # fatal error. A keyring rollout has to land first.
        log.warn(
            "archlinux packages are UNSIGNED: nfpm cannot sign them, and publishing "
            "a .sig before a keyring rollout would break pacman -U (see "
            "check-release-signing-coverage.sh)"
        )


def build(argv: list[str]) -> int:
    """The twin, top to bottom, in its order. See `build_cli_executables.build`
    for why this is deliberately not decomposed into a helper per phase."""
    source_common()

    values, dry_run, wants_help = parse_args(argv)
    if wants_help:
        print(
            "Usage: %s --binary PATH --version VER --arch ARCH --format FORMAT "
            "[--output DIR] [--dry-run]" % sys.argv[0],
            flush=True,
        )
        return 0

    # `:75-80`. The FIRST missing one wins; the loop exits rather than collecting.
    for name in ("BINARY", "VERSION", "ARCH", "FORMAT"):
        if not values[name]:
            raise Refusal(1, "✗ Missing required argument: --%s" % name.lower())

    binary = values["BINARY"]
    version = values["VERSION"]
    arch = values["ARCH"]
    fmt = values["FORMAT"]
    output_dir = values["OUTPUT"]

    if fmt not in FORMATS:
        raise Refusal(
            1,
            "✗ Invalid format '%s'. Must be one of: deb, rpm, apk, archlinux" % fmt,
        )
    if arch not in ARCH_MAP:
        raise Refusal(
            1,
            "✗ Invalid architecture '%s'. Must be one of: amd64, arm64, x86_64, aarch64" % arch,
        )

    arch_names = ARCH_MAP[arch]
    nfpm_arch = arch_names[0]
    pkg_file = package_filename(fmt, version, arch_names)

    root = console_root()
    if not output_dir:
        output_dir = str(root / "dist" / "packages")

    log.step("Building .%s package: %s" % (fmt, pkg_file))
    log.info("  Binary: %s" % binary)
    log.info("  Version: %s" % version)
    log.info("  Arch: %s (nfpm: %s)" % (arch, nfpm_arch))
    log.info("  Format: %s" % fmt)
    log.info("  Output: %s/%s" % (output_dir, pkg_file))

    if dry_run:
        # DEFECT 5: this is ABOVE both validations, on purpose per the twin's own
        # comment. A preview therefore cannot tell you the binary is missing.
        log.info("[DRY-RUN] Would build %s" % pkg_file)
        _run(["mkdir", "-p", output_dir], 148)
        return 0

    require_file(binary)
    require_cmd("nfpm")

    # `:161-167`. nfpm.yaml is a TEMPLATE over these; the child must see them.
    os.environ["PKG_NAME"] = PKG_NAME
    os.environ["PKG_BINARY_NAME"] = PKG_BINARY_NAME
    os.environ["PKG_SECTION"] = PKG_SECTION
    os.environ["PKG_PRIORITY"] = PKG_PRIORITY
    os.environ["PKG_MAINTAINER"] = PKG_MAINTAINER
    os.environ["PKG_DESCRIPTION"] = PKG_DESCRIPTION
    os.environ["PKG_HOMEPAGE"] = PKG_HOMEPAGE
    os.environ["VERSION"] = version
    os.environ["NFPM_ARCH"] = nfpm_arch

    # `:166`. BINARY_PATH must be ABSOLUTE for nfpm, and the twin spells that as
    # `$(cd "$(dirname "$BINARY")" && pwd)/$(basename "$BINARY")` -- a command
    # substitution nested two levels deep, whose `cd` failing would be a silent
    # `set -e` death. It cannot fail here because `require_file` above already
    # proved the file exists, so the directory does too; the nesting is recorded
    # because two-level nesting is exactly the shape that hides a refusal.
    os.environ["BINARY_PATH"] = os.path.join(
        os.path.abspath(os.path.dirname(binary) or "."), os.path.basename(binary)
    )

    build_dir = tempfile.mkdtemp()
    try:
        return _build_in(fmt, pkg_file, output_dir, build_dir, root)
    finally:
        # `trap cleanup EXIT`. Runs on every path below, refusals included.
        shutil.rmtree(build_dir, ignore_errors=True)


def _build_in(
    fmt: str,
    pkg_file: str,
    output_dir: str,
    build_dir: str,
    root: pathlib.Path,
) -> int:
    """`:177-345`, everything the EXIT trap is responsible for cleaning up after.

    Split out from `build()` for ONE reason: the twin's `trap cleanup EXIT` fires
    on every path from `:175` onward, and a `finally` around a call expresses
    that where a `finally` wrapped around half a function body does not.
    """
    signing_configured = False

    if fmt in ("rpm", "deb") and os.environ.get("RELEASE_GPG_PRIVATE_KEY", ""):
        _setup_gpg_signing(fmt, build_dir, root)
        signing_configured = True
    elif fmt == "apk" and os.environ.get("APK_RSA_PRIVATE_KEY", ""):
        log.info("Setting up RSA signing for APK...")
        apk_key_file = os.path.join(build_dir, "apk-signing-key.rsa")
        with open(apk_key_file, "w", encoding="utf-8") as handle:
            handle.write(_bash_echo(os.environ.get("APK_RSA_PRIVATE_KEY", "")))
        os.environ["NFPM_APK_KEY_FILE"] = apk_key_file
        signing_configured = True

    nfpm_config = str(root / NFPM_CONFIG_REL)
    _run(["mkdir", "-p", output_dir], 266)

    _run(
        [
            "nfpm",
            "package",
            "--config",
            nfpm_config,
            "--packager",
            fmt,
            "--target",
            build_dir + "/",
        ],
        268,
    )

    # `:277-279`. nfpm names files its own way; find the one it wrote and rename.
    # DIRECTORY ORDER, not sorted: see DEFECT 3 and the module head. `_capture_or_die`
    # rather than `_capture`, because this is an ASSIGNMENT of a pipeline and a
    # `find` that exits 1 kills the twin outright with nothing said.
    found = _capture_or_die(
        [
            "find",
            build_dir,
            "-maxdepth",
            "1",
            "-type",
            "f",
            "(",
            *_name_predicates(),
            ")",
        ]
    )
    built_pkg = found.split("\n")[0] if found else ""
    if not built_pkg:
        raise Refusal(1, "✗ nfpm produced no output file")

    _run(["cp", built_pkg, os.path.join(output_dir, pkg_file)], 286)

    # DEFECT 4: unreachable, because the `cp` above is unguarded under `set -e`.
    # Kept so the two files read the same way.
    target = pathlib.Path(output_dir) / pkg_file
    if not target.is_file():
        raise Refusal(1, "✗ Package build failed: %s not found" % pkg_file)

    package_size = target.stat().st_size
    log.info("Package built: %s (%dKB)" % (pkg_file, package_size // 1024))

    if signing_configured:
        # DEFECT 6: this says a key was CONFIGURED, not that nfpm signed anything,
        # and for apk it calls an RSA key an "APK key".
        log.info("Package signed with %s key" % fmt.upper())
    else:
        _report_unsigned(fmt)
    return 0


def _name_predicates() -> list[str]:
    """`-name "*.deb" -o -name "*.rpm" -o ...`, built from `PACKAGE_GLOBS`."""
    out: list[str] = []
    for glob in PACKAGE_GLOBS:
        if out:
            out.append("-o")
        out += ["-name", glob]
    return out


def main(argv: list[str]) -> int:
    try:
        return build(argv)
    except Refusal as refusal:
        for line in refusal.lines:
            print(line, file=sys.stderr, flush=True)
        return refusal.code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
