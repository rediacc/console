#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-pkg-repo.sh`.

Builds four self-contained package repositories -- APT, RPM, Alpine APK and
Arch Linux -- out of an already built directory of `.deb`, `.rpm`, `.apk` and
`.pkg.tar.zst` files, and GPG-signs the two that clients verify. "Self
contained" is the whole design: the packages sit alongside their metadata, so
nothing in a published repository points at an external URL.

Five phases, numbered 1, 4, 5, 6, 7 in the twin's own headings. Phases 2 and 3
were the "download historical versions" steps and are gone; the numbering was
left alone, and this port leaves it alone too, because the numbers appear in
`log_step` output that a workflow log reader greps for.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT, because the tool IS the behaviour and a Python second opinion
would be a second source of truth for what gets published:

  * `gpg`, six ways: `--import`, `--list-keys --with-colons`, `--show-keys
    --with-colons --with-fingerprint`, `--detach-sign --armor`, `--clearsign`
    and `--armor --export`. The fingerprint COMPARISON is the check that stops
    a repository being signed with a key no apt or dnf client trusts.
  * `dpkg-scanpackages`, which produces the `Packages` index. Its output is
    hashed into `Release` and then signed, so a reimplementation would change
    what clients verify.
  * `createrepo_c`, same argument for `repodata/`.
  * `docker run alpine:latest ... apk index` and `docker run archlinux:latest
    ... repo-add`. Those two images own the APKINDEX and pacman database
    formats.
  * `gzip -9c`. NOT `gzip.open`: gzip embeds the SOURCE FILE'S mtime and its
    basename in the member header, and the resulting bytes are what `Release`
    records an md5 and a sha256 of. Python's `gzip` module writes a different
    header for the same input, so a port that compressed in-process would ship
    a `Packages.gz` whose checksum a byte-comparing reader could not reproduce
    from the twin. (The mtime in that header is also why two runs SECONDS APART
    produce different `Packages.gz` bytes on either side; the differential
    normalises for it and says so.)
  * `tar xzf ... -O APKINDEX`. Kept as a subprocess specifically so DEFECT 1
    below reproduces: the twin's silent death there is `tar`'s exit status, and
    a `tarfile` call raising a Python exception would be a different program.
  * `date -Ru` / `date -u -d @EPOCH -R`. RFC-2822 in the C locale is what an
    apt client parses out of `Release`, and `email.utils.format_datetime`
    disagrees with GNU date on the zone spelling (`+0000` versus `GMT`).
  * `find`, for every enumeration and for the four `-exec cp {} DIR/ \\;`
    copies. Not `Path.glob`: `find` returns DIRECTORY ORDER, and the apk phase
    copies several files to a name derived from ONE index entry (DEFECT 7), so
    WHICH file wins the collision is decided by that order. A sorted Python
    glob would pick a different winner. Same reasoning as
    `build_linux_pkg.py`'s `find | head -1`.
  * `uname -s` / `uname -m`, because sourcing `common.sh` costs them; see
    `source_common`.

NOT SHELLED OUT, because these are pure and deterministic:

  * `md5sum` / `sha256sum` -> `hashlib`. A digest is a digest.
  * `wc -c` -> `stat().st_size`; `wc -l` -> a newline count over `find`'s
    stdout, which is what `wc -l` counts and is NOT the same as "number of
    files" when a filename contains a newline. The twin miscounts there too.
  * `mktemp -d` -> `tempfile.mkdtemp(prefix="tmp.")`, and `trap cleanup EXIT`
    -> a `finally`. The prefix matches `mktemp`'s template shape on purpose:
    the APT pool's temp path is INTERPOLATED INTO THE VACUITY REFUSAL at `:214`,
    so it is observable output, and the differential masks only the random
    suffix rather than the whole path.
  * `cat > file <<EOF` -> a file write. The two heredocs (`rediacc.repo`,
    `rediacc.conf`) are expanded, so `${RELEASES_BASE_URL}` and `${CHANNEL}`
    interpolate while archlinux's `\\$arch` stays literal for pacman.
  * The `[[ "$DEB_COUNT" -lt "$MIN_DEBS" ]]` comparison -> `bash_lt` below,
    which reproduces bash's arithmetic grammar rather than `int()`. That is not
    pedantry; it is DEFECT 3.
  * `.ci/config/constants.sh`. Restated, the way `build_linux_pkg.py` and
    `docker/create_manifest.py` restate theirs, with
    `test_the_restated_constants_match_constants_sh` parsing the real file and
    failing on drift. Note the two are NOT the same kind of constant:
    `PKG_NAME` is a bare `readonly`, so the environment cannot reach it, while
    `RELEASES_BASE_URL` is `readonly X="${X:-default}"`, so it CAN be
    overridden. The port keeps that asymmetry.

-----------------------------------------------------------------------------
SEVEN REAL DEFECTS IN THE TWIN, REPRODUCED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
Every one below was DRIVEN against the real script, not inferred from reading.
The line numbers are the live ones.

DEFECT 1 -- THE WARN-AND-CONTINUE PATH DOES NOT CONTINUE. `:389`:

    apk_name=$(tar xzf "$APK_DIR/$arch/APKINDEX.tar.gz" -O APKINDEX 2>/dev/null | awk ...)

An assignment whose right-hand side is a PIPELINE, under `set -o pipefail`.
When docker is absent the branch above it prints `Docker not available, cannot
generate APKINDEX for x86_64` and falls through -- but no `APKINDEX.tar.gz`
exists, `tar` exits 2, `awk` exits 0, pipefail makes the pipeline 2 and `set -e`
kills the script THERE. Measured: exit 2, the last line on stderr is that
warning, no packages are copied, phase 7 never runs and the summary never
prints. So the machine every developer would run this on -- one without docker
-- gets a repository with an empty `apk/<arch>/` directory and a failure it
cannot diagnose. Reproduced, including the status.

DEFECT 2 -- THE VACUITY FLOOR COVERS APT AND NOTHING ELSE. `:212-217` refuses
an empty `.deb` pool with a written-out explanation. RPM, APK and archlinux have
no equivalent. Measured with a `--local-pkgs` holding ONE `.deb` and nothing
else: exit 0, `rpm/repodata/repomd.xml` generated AND SIGNED over zero packages,
`archlinux/rediacc.conf` written, and the summary reports "metadata for 0 .rpm
packages" in the same tick-prefixed green as everything else. A partial build
publishes three empty repositories and says it succeeded. Reproduced.

DEFECT 3 -- THE FLOOR IS DISABLED BY A ZERO-PADDED VALUE. `:213` compares with
`[[ "$DEB_COUNT" -lt "$MIN_DEBS" ]]`, which is bash ARITHMETIC, which reads a
leading zero as octal. `PKG_REPO_MIN_DEBS=08` is not a number in base 8, so bash
prints `line 213: [[: 08: value too great for base (error token is "08")` and
the `[[` returns FALSE -- an error is FALSE, not zero -- so the refusal is
SKIPPED. Measured on an empty package directory: `PKG_REPO_MIN_DEBS=1` exits 1
and refuses, `PKG_REPO_MIN_DEBS=8` exits 1 and refuses, `PKG_REPO_MIN_DEBS=08`
exits 0 and publishes an empty APT repository. `PKG_REPO_MIN_DEBS=0` also
disables it, which is at least legible. Same class as this session's
`autopilot-gate.sh`, `dispatch-watchdog.sh` and `cleanup-versions.sh` findings.
Reproduced by `bash_lt`, which returns False on an arithmetic error for exactly
the reason `autopilot_gate.bash_cmp` does.

DEFECT 4 -- `--dry-run` IS NOT A PREVIEW, AND THE TWO CONFIG WRITERS DISAGREE
ABOUT WHAT IT MEANS. `:324-331` writes `rpm/rediacc.repo` OUTSIDE the dry-run
guard; `:451` writes `archlinux/rediacc.conf` INSIDE it. Driving `--dry-run`
produces `rpm/rediacc.repo` and no `archlinux/rediacc.conf`, which is the
inconsistency as reported. It is WORSE than that, and this port records the
extra half: `:300`, the `find ... -name "*.rpm" -exec cp {} "$RPM_DIR/"` that
populates the RPM repository, is ALSO outside the guard, so a "preview" run
copies the real `.rpm` payload into the output directory. Measured: after
`--dry-run` the output tree holds two `.rpm` files plus `rediacc.repo`. The APT
phase does not have this problem only because its copy targets a temp pool the
EXIT trap deletes. Reproduced exactly, both halves.

DEFECT 5 -- `--max-versions` WITH NO VALUE DIES WITH ZERO BYTES ON BOTH STREAMS.
`:51-54` is a deprecated no-op arm that still does `shift 2`. Given one
remaining argument, `shift 2` fails, and under `set -e` that ends the script.
Measured: exit 1, 0 bytes on stdout, 0 bytes on stderr. Every OTHER flag in the
parser dies with a named `<script>: line N: $2: unbound variable` -- `--version`
names line 40, `--channel` names line 56. A silent exit 1 is indistinguishable
from a gate failing for a real reason, which is precisely the shape this
campaign keeps finding. Reproduced, silence included.

DEFECT 6 -- THE SIGNING-KEY CHECK'S OWN `<unreadable>` FALLBACK IS DEAD CODE.
`:161-162` are two more assignments-of-a-pipeline:

    want_fpr=$(gpg --show-keys ... "$PUBLIC_KEY_FILE" 2>/dev/null | awk ...)
    have_fpr=$(gpg --list-keys ... "$GPG_KEY_ID" 2>/dev/null | awk ...)

Same shape as `build-linux-pkg.sh:226-227`, and the same consequence: gpg exits
2 on a file that is not a key, `awk` exits 0, pipefail makes the pipeline 2 and
the script dies before `:164` can print `${want_fpr:-<unreadable>}`. Measured
with a gpg that refuses `--show-keys`: exit 2, 0 bytes on stdout, and the last
line on stderr is `Using GPG key: DEADBEEF` -- a build that says it found the
key and then vanishes. The MISMATCH branch itself is live and was driven
separately (two different fingerprints produce the full refusal at exit 1), so
this is a dead fallback inside a working check, not a dead check. Reproduced.

DEFECT 7 -- TWO APKS FOR ONE ARCH COLLAPSE INTO ONE FILE, SILENTLY. `:387-395`
loops over every `.apk` for an arch and, for EACH ONE, recomputes `apk_name`
from the same `APKINDEX.tar.gz` with an awk program that `exit`s after the FIRST
`V:` line. So every file in the loop is copied to the SAME destination name and
each overwrites the last. Measured with two `.apk` files for x86_64: exit 0, no
warning, and `apk/x86_64/` holds ONE package. Found by driving, not by reading.
Reproduced.

NOT A DEFECT, AND WORTH SAYING SO: the `find ... -exec cp` at `:202` is silent
when it matches nothing, and the twin's comment at `:207-211` says so in as many
words -- which is why the APT floor exists at all. The floor is the right idea;
DEFECT 2 is that it was never extended to the other three.

-----------------------------------------------------------------------------
TWO DIVERGENCES, NAMED RATHER THAN HIDDEN
-----------------------------------------------------------------------------
1. THE INTERPRETER'S OWN DIAGNOSTICS. bash prefixes `<script path>: line <n>: `
   to `$2: unbound variable` and to the `[[: 08:` arithmetic error. A Python
   process cannot produce the twin's path and line, so this port prints the same
   sentences with its OWN `argv[0]`. Exit code, stdout, artifacts and the
   DECISION are identical; one stderr prefix differs. Pinned by
   `test_a_missing_flag_value_names_the_program_that_refused` and
   `test_a_zero_padded_floor_disables_the_refusal`, which mask the prefix,
   compare the rest byte for byte, and then assert the unmasked strings DIFFER
   so the mask cannot start hiding a real change.

2. THE TEMP DIRECTORY NAME. `mktemp -d` and `tempfile.mkdtemp(prefix="tmp.")`
   agree on shape and disagree on the random suffix. It is observable in exactly
   one place, the vacuity refusal at `:214`, and the differential masks the
   suffix only.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE
-----------------------------------------------------------------------------
`RELEASE_GPG_PRIVATE_KEY`, `RELEASE_GPG_PASSPHRASE`,
`RELEASE_GPG_PUBLIC_KEY_FILE`, `PKG_REPO_MIN_DEBS`, `SOURCE_DATE_EPOCH` and
`RELEASES_BASE_URL` are each read with a direct `os.environ.get("NAME", ...)`
where they are used. No dict alias and no loop: the env-manifest reader parses
direct reads by name, and an alias hides them.
"""

from __future__ import annotations

import contextlib
import glob as globmod
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log

# ---------------------------------------------------------------------------
# `.ci/config/constants.sh`, RESTATED. Two DIFFERENT kinds of constant, and the
# difference is load-bearing:
#
#   readonly PKG_NAME="rediacc-cli"                       -- environment CANNOT
#                                                            override it
#   readonly RELEASES_BASE_URL="${RELEASES_BASE_URL:-...}" -- environment CAN
#
# `test_the_restated_constants_match_constants_sh` parses the real file and
# fails on drift in either.
# ---------------------------------------------------------------------------
PKG_NAME = "rediacc-cli"
RELEASES_BASE_URL_DEFAULT = "https://releases.rediacc.com"

# `:148`. The published public key, and its environment override.
DEFAULT_PUBLIC_KEY_REL = ".ci/keys/gpg-public.asc"

# `:212`. The floor's default, as a STRING, because the comparison that consumes
# it is bash arithmetic over a string and not an integer comparison.
DEFAULT_MIN_DEBS = "1"

# `:225`, `:257`, `:268`. Debian architecture names, in the twin's order. Order
# is observable: it decides the order of the checksum rows in `Release`.
APT_ARCHES = ("amd64", "arm64")

# `:344`, `:411`. Alpine and Arch name the same two machines differently from
# nfpm, and the apk phase has to translate while the archlinux phase does not.
APK_ARCHES = (("x86_64", "amd64"), ("aarch64", "arm64"))
ARCHLINUX_ARCHES = ("x86_64", "aarch64")

# `:39-58`. The flags whose value is `$2`, and the LINE the twin dies on when it
# is missing. `--max-versions` is deliberately absent: it has no `$2` reference
# at all, only a `shift 2`, which is DEFECT 5.
VALUE_FLAG_LINES = {
    "--version": 40,
    "--local-pkgs": 44,
    "--output": 48,
    "--channel": 56,
}

# `:213`. Where the arithmetic error is reported from, for the diagnostic.
FLOOR_LINE = 213


class Refusal(Exception):  # noqa: N818 - named for what the twin does
    """A `log_error ...; exit N`, or a bare `set -e` death when `lines` is empty.

    THE EMPTY CASE IS NOT A SHORTCUT. DEFECTS 1, 5 and 6 are all places where the
    twin genuinely exits non-zero having printed nothing at all, and a port that
    invented a message there would be describing a better program than the one
    that runs.

    `raw=True` marks a diagnostic the INTERPRETER emits rather than the script:
    it goes to stderr unadorned, with no `log_error` tick, because bash's
    `$2: unbound variable` does not wear one either.
    """

    def __init__(self, code: int, *lines: str, raw: bool = False) -> None:
        super().__init__(lines[0] if lines else "")
        self.code = code
        self.lines = lines
        self.raw = raw


# ---------------------------------------------------------------------------
# common.sh, the parts this script reaches
# ---------------------------------------------------------------------------


def console_root() -> pathlib.Path:
    """`get_repo_root` (`common.sh:205-210`), which has no environment override.

    `rediacc_ci.paths.repo_root()` honours `$REDIACC_CI_ROOT` and is deliberately
    NOT used: a differential where one side follows an override and the other
    does not diverges for a reason that says nothing about the port. Same
    derivation as `build_linux_pkg.py` and `build_linux_packages.py`.
    """
    # This file: <root>/.ci/rediacc_ci/build/build_pkg_repo.py
    return pathlib.Path(__file__).resolve().parents[3]


def _capture(argv: list[str]) -> str:
    """`$(cmd)` -- stdout with trailing newlines stripped, stderr inherited."""
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, check=False)
    except OSError:
        return ""
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


def source_common() -> None:
    """`common.sh:504-514` -- two `uname` processes and three exported variables.

    Not a function in the twin: SOURCING the library runs it, so this happens
    before line 28 of the script and every child it later spawns (gpg,
    dpkg-scanpackages, createrepo_c, docker, tar, gzip, date) inherits `CI_OS`,
    `CI_ARCH` and `CI_TEMP`. A port that skipped it would hand those children a
    different environment, and the difference would show up as a divergence
    nobody could attribute. Duplicated in this wave's sibling ports on purpose;
    see `build_cli_executables.source_common` for the note on lifting it.
    """
    os.environ["CI_OS"] = _detect_os()
    os.environ["CI_ARCH"] = _detect_arch()
    os.environ["CI_TEMP"] = (
        os.environ.get("RUNNER_TEMP", "") or os.environ.get("TMPDIR", "") or "/tmp"
    )


def require_dir(path: str) -> None:
    """`common.sh:160-167`, verbatim."""
    if not pathlib.Path(path).is_dir():
        raise Refusal(1, "Required directory '%s' does not exist" % path)


def require_cmd(cmd: str) -> None:
    """`common.sh:140-147`, verbatim."""
    if shutil.which(cmd) is None:
        raise Refusal(1, "Required command '%s' is not available" % cmd)


# ---------------------------------------------------------------------------
# bash arithmetic, which is not int()
# ---------------------------------------------------------------------------


def bash_arith(text: str) -> int | None:
    """`$((text))` for a bare token. `None` means bash raised an ERROR.

    The grammar, and only the parts a value reaching `:213` can exhibit:

        ""        0     an empty or unset variable is zero
        "0"       0
        "007"     7     LEADING ZERO IS OCTAL
        "0x10"   16
        "08"   None     an invalid octal digit is an ERROR
        "abc"     0     a bare word is a variable name; unset names are zero
        " 5 "     5     the operand is trimmed before evaluation

    Measured against bash 5.3.9 for each row above, not inferred. `1+1` and
    `3.5` are genuinely out of scope -- the first evaluates to 2 in bash and to
    an error here, the second errors in both with a different message -- and
    `PKG_REPO_MIN_DEBS` reaching this function as an EXPRESSION rather than a
    literal is not a case any caller produces. Named so a future reader does not
    mistake the boundary for a bug.

    THE `None` IS THE WHOLE POINT, and it is DEFECT 3. An erroring `[[ ]]`
    returns FALSE, and false is not "compare against zero": a port that read
    `08` as `0` would compute `0 -lt 0`, get False, and reach the same answer by
    luck on this one input while getting `[[ 0 -lt 09 ]]` exactly backwards.
    Same shape and same reasoning as `autopilot_gate.bash_arith`.
    """
    token = text.strip()
    if token == "":
        return 0
    negative = False
    if token[0] in "+-":
        negative = token[0] == "-"
        token = token[1:]
    if token == "":
        return 0
    try:
        if token[:2].lower() == "0x":
            value = int(token, 16)
        elif token[0] == "0" and len(token) > 1:
            value = int(token[1:], 8)
        else:
            value = int(token, 10)
    except ValueError:
        if token[0].isdigit():
            # bash: `<script>: line 213: [[: 08: value too great for base
            # (error token is "08")`. This copy carries THIS program's name
            # instead of the twin's path; see divergence 1 in the module head.
            print(
                '%s: line %d: [[: %s: value too great for base (error token is "%s")'
                % (sys.argv[0], FLOOR_LINE, token, token),
                file=sys.stderr,
                flush=True,
            )
            return None
        # A bare word is a variable name. Nothing sets it, so it is zero.
        return 0
    return -value if negative else value


def bash_lt(left: str, right: str) -> bool:
    """`[[ left -lt right ]]`, including "an arithmetic error is FALSE".

    bash evaluates left to right and stops at the first bad token, so only ONE
    diagnostic is printed even when both operands are malformed. Reproduced,
    because those diagnostics are on stderr and the differential compares stderr.
    """
    a = bash_arith(left)
    if a is None:
        return False
    b = bash_arith(right)
    if b is None:
        return False
    return a < b


# ---------------------------------------------------------------------------
# subprocess shapes the twin uses, each preserving its own failure semantics
# ---------------------------------------------------------------------------


def _bare(argv: list[str], **kw) -> None:
    """A bare command under `set -e`. Its status PROPAGATES, unflattened.

    An exec failure is bash's 127 ("command not found") or 126 ("cannot
    execute"), and bash says so on stderr against its own path and line. The
    STATUS is reproduced exactly; the diagnostic carries this program's name
    instead, which is divergence 1 in the module head.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        code = subprocess.run(argv, check=False, **kw).returncode
    except PermissionError:
        print("%s: %s: Permission denied" % (sys.argv[0], argv[0]), file=sys.stderr, flush=True)
        code = 126
    except OSError:
        print("%s: %s: command not found" % (sys.argv[0], argv[0]), file=sys.stderr, flush=True)
        code = 127
    if code != 0:
        raise Refusal(code)


def _find(root: str, name: str, *, quiet: bool = False) -> list[str]:
    """`find ROOT -name NAME`, as a list of lines.

    `quiet` is the twin's `2>/dev/null || true`: those call sites cannot die, so
    a failure here yields an empty list. Where the twin has no `|| true` the
    caller uses `_find_strict` instead, because there the status kills.
    """
    try:
        proc = subprocess.run(
            ["find", root, "-name", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet else None,
            check=False,
        )
    except OSError:
        return []
    text = proc.stdout.decode("utf-8", errors="replace")
    return [line for line in text.split("\n") if line]


def _count(root: str, name: str, *, quiet: bool = False) -> str:
    """`$(find ROOT -name NAME | wc -l || true)`, as the STRING the twin holds.

    A string, not an int, because it is interpolated into log lines and into the
    arithmetic at `:213` without ever being normalised. `wc -l` counts NEWLINES,
    which is what this counts; a filename containing a newline over-counts on
    both sides, identically.
    """
    return str(len(_find(root, name, quiet=quiet)))


def _find_exec_cp(root: str, name: str, dest: str, *, quiet: bool = False) -> None:
    """`find ROOT -name NAME -exec cp {} DEST/ \\;`.

    Shelled out whole rather than enumerate-then-`shutil.copy`, so the copy
    happens in `find`'s DIRECTORY ORDER. That is not cosmetic: when two files
    would land on the same name, order decides the winner, which is exactly
    DEFECT 7's mechanism one directory over.

    `quiet=True` is `2>/dev/null || true`, which the apk and archlinux phases
    have and the deb and rpm phases do NOT -- so a `find` failure kills the
    script in phases 4 and 5 and is swallowed in phases 6 and 7. Preserved.
    """
    argv = ["find", root, "-name", name, "-exec", "cp", "{}", dest + "/", ";"]
    if quiet:
        with contextlib.suppress(OSError):
            subprocess.run(argv, stderr=subprocess.DEVNULL, check=False)
        return
    _bare(argv)


def _gpg(gpg_opts: list[str], *args: str) -> None:
    """`gpg "${GPG_OPTS[@]}" ...` as a bare command under `set -e`."""
    _bare(["gpg", *gpg_opts, *args])


def _first_field(output: str, want: str, index: int) -> str:
    """`awk -F: '$1=="want"{print $<index>; exit}'`, reimplemented.

    Four tokens of text processing, not a tool whose behaviour is under test.
    `index` is 1-based, matching awk.
    """
    for line in output.split("\n"):
        fields = line.split(":")
        if fields and fields[0] == want:
            return fields[index - 1] if len(fields) >= index else ""
    return ""


def _fingerprint(argv: list[str]) -> str:
    """`$(gpg ... 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}')`.

    DEFECT 6 LIVES HERE AND IS WHY THIS IS A FUNCTION. The twin writes the gpg
    call as the right-hand side of an assignment, which makes the PIPELINE's
    status the assignment's status; under `pipefail` a gpg that exits non-zero
    kills the script with no output at all, so the `<unreadable>` fallback two
    lines later can never be reached. `awk` always exits 0, so gpg's status is
    the only one that can be non-zero.
    """
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    except OSError:
        raise Refusal(127) from None
    if proc.returncode != 0:
        raise Refusal(proc.returncode)
    return _first_field(proc.stdout.decode("utf-8", errors="replace"), "fpr", 10)


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> tuple[dict[str, str], bool, bool]:
    """`:37-72`. Returns `(values, dry_run, wants_help)`.

    Every refusal in here is the SHELL's, not the script's, apart from the
    `*)` arm. Two shapes:

      * a value flag with nothing after it -> `$2: unbound variable` naming the
        assignment's line, exit 1;
      * `--max-versions` with nothing after it -> `shift 2` fails and `set -e`
        ends the run with ZERO BYTES on both streams, exit 1. That is DEFECT 5,
        and the empty `Refusal` is how it is spelled.
    """
    values = {"VERSION": "", "LOCAL_PKGS": "", "OUTPUT_DIR": "", "CHANNEL": ""}
    keys = {
        "--version": "VERSION",
        "--local-pkgs": "LOCAL_PKGS",
        "--output": "OUTPUT_DIR",
        "--channel": "CHANNEL",
    }
    dry_run = False
    rest = list(argv)
    while rest:
        flag = rest[0]
        if flag in keys:
            if len(rest) < 2:
                raise Refusal(
                    1,
                    "%s: line %d: $2: unbound variable" % (sys.argv[0], VALUE_FLAG_LINES[flag]),
                    raw=True,
                )
            values[keys[flag]] = rest[1]
            rest = rest[2:]
        elif flag == "--max-versions":
            # Deprecated: ignored (historical versions accumulate via s3 sync).
            # DEFECT 5: `shift 2` with one argument left is a silent death.
            if len(rest) < 2:
                raise Refusal(1)
            rest = rest[2:]
        elif flag == "--dry-run":
            dry_run = True
            rest = rest[1:]
        elif flag in ("-h", "--help"):
            return values, dry_run, True
        else:
            raise Refusal(1, "Unknown option: %s" % flag)
    return values, dry_run, False


# ---------------------------------------------------------------------------
# phases
# ---------------------------------------------------------------------------


def _phase1_gpg(
    output_dir: str, dry_run: bool, gpg_opts: list[str], cleanup_dirs: list[str]
) -> str:
    """`:105-179`. Import the signing key and PROVE it is the published one.

    Returns the key id, which is `""` under `--dry-run` and is then passed to
    nothing, because every consumer of it sits inside a non-dry-run branch.
    """
    log.step("Phase 1: GPG setup")

    for name in ("apt", "rpm", "apk", "archlinux"):
        pathlib.Path(output_dir, name).mkdir(parents=True, exist_ok=True)

    if dry_run:
        log.info("[DRY-RUN] Skipping GPG setup")
        return ""

    private_key = os.environ.get("RELEASE_GPG_PRIVATE_KEY", "")
    if not private_key:
        raise Refusal(1, "RELEASE_GPG_PRIVATE_KEY environment variable is required")

    gnupghome = tempfile.mkdtemp(prefix="tmp.")
    os.environ["GNUPGHOME"] = gnupghome
    cleanup_dirs.append(gnupghome)

    # `echo "$KEY" | gpg ... --import 2>/dev/null`. A PIPELINE as a command, not
    # as an assignment, so pipefail plus `set -e` kills on a failed import --
    # with the diagnostic thrown away by the `2>/dev/null`.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        imported = subprocess.run(
            ["gpg", *gpg_opts, "--import"],
            input=(private_key + "\n").encode("utf-8"),
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
    except OSError:
        imported = 127
    if imported != 0:
        raise Refusal(imported)
    log.info("GPG private key imported")

    # `$(gpg --list-keys --with-colons 2>/dev/null | grep '^pub' | head -1 |
    # cut -d: -f5 || true)`. The `|| true` is what stops this one being a
    # DEFECT-6 death, so a missing gpg lands on the refusal below instead.
    try:
        listed = subprocess.run(
            ["gpg", "--list-keys", "--with-colons"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        ).stdout
    except OSError:
        listed = b""
    key_id = ""
    for line in listed.decode("utf-8", errors="replace").split("\n"):
        if line.startswith("pub"):
            fields = line.split(":")
            key_id = fields[4] if len(fields) >= 5 else ""
            break
    if not key_id:
        raise Refusal(1, "No GPG public key found after import")
    log.info("Using GPG key: %s" % key_id)

    public_key_file = os.environ.get("RELEASE_GPG_PUBLIC_KEY_FILE", "") or str(
        console_root() / DEFAULT_PUBLIC_KEY_REL
    )

    # THE PUBLISHED PUBLIC KEY MUST BE THE SIGNING KEY. Until 2026-09-04 nothing
    # checked that, and a rotation applied to the secret store and not to the
    # file would have shipped a repository every apt and dnf client rejects
    # while this script said "GPG private key imported" and exited 0.
    if pathlib.Path(public_key_file).is_file():
        want_fpr = _fingerprint(
            ["gpg", "--show-keys", "--with-colons", "--with-fingerprint", public_key_file]
        )
        have_fpr = _fingerprint(
            ["gpg", "--list-keys", "--with-colons", "--with-fingerprint", key_id]
        )
        if not want_fpr or not have_fpr or want_fpr != have_fpr:
            # DEFECT 6: `${want_fpr:-<unreadable>}` and `${have_fpr:-<none>}`
            # are written for a case `_fingerprint` has already died on. Kept
            # verbatim so the two files read the same way.
            raise Refusal(
                1,
                "signing key %s is not the published public key %s (%s); a repository "
                "signed with it would fail verification on every client"
                % (have_fpr or "<none>", want_fpr or "<unreadable>", public_key_file),
            )
        log.info("Signing key matches the published public key (%s)" % want_fpr)

    if pathlib.Path(public_key_file).is_file():
        shutil.copy(public_key_file, os.path.join(output_dir, "apt", "gpg.key"))
        shutil.copy(public_key_file, os.path.join(output_dir, "rpm", "gpg.key"))
        log.info("Copied public key from %s" % public_key_file)
    else:
        for name in ("apt", "rpm"):
            with open(os.path.join(output_dir, name, "gpg.key"), "wb") as handle:
                _bare(["gpg", "--armor", "--export", key_id], stdout=handle)
        log.warn("No public key file found at %s, exported from keyring" % public_key_file)
    return key_id


def _release_date() -> str:
    """`:237-241`. `date -u -d @EPOCH -R` with a `date -Ru` fallback.

    `$(A 2>/dev/null || B)` -- the fallback catches a `date` that cannot parse
    the epoch, which is what a non-GNU `date` does.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "")
    if epoch:
        try:
            proc = subprocess.run(
                ["date", "-u", "-d", "@%s" % epoch, "-R"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            proc = None
        if proc is not None and proc.returncode == 0:
            return proc.stdout.decode("utf-8", errors="replace").rstrip("\n")
    return _capture(["date", "-Ru"])


def _checksum_rows(dists_dir: str, algorithm: str) -> list[str]:
    """`:257-262` and `:268-273`, the two identical loops over one glob pair.

    bash expands `main/binary-*/Packages main/binary-*/Packages.gz` in collation
    order and leaves an unmatched pattern LITERAL, which the `[[ -f ]]` then
    skips. Reproduced with a sorted glob and an `is_file` test, because a
    Release that lists a file it does not have breaks `apt update` on every
    client.
    """
    rows: list[str] = []
    previous = os.getcwd()
    os.chdir(dists_dir)
    try:
        for pattern in ("main/binary-*/Packages", "main/binary-*/Packages.gz"):
            for name in sorted(globmod.glob(pattern)):
                path = pathlib.Path(name)
                if not path.is_file():
                    continue
                digest = hashlib.new(algorithm, path.read_bytes()).hexdigest()
                rows.append(" %s %d %s" % (digest, path.stat().st_size, name))
    finally:
        os.chdir(previous)
    return rows


def _phase4_apt(
    local_pkgs: str,
    output_dir: str,
    dry_run: bool,
    gpg_opts: list[str],
    key_id: str,
    cleanup_dirs: list[str],
) -> tuple[str, str]:
    """`:184-287`. Returns `(apt_dir, deb_count)`."""
    log.step("Phase 4: Building APT repository metadata")

    apt_dir = os.path.join(output_dir, "apt")
    dists_dir = os.path.join(apt_dir, "dists", "stable")

    apt_work_dir = tempfile.mkdtemp(prefix="tmp.")
    apt_pool_dir = os.path.join(apt_work_dir, "pool", "main", "r", PKG_NAME)
    cleanup_dirs.append(apt_work_dir)

    pathlib.Path(apt_pool_dir).mkdir(parents=True, exist_ok=True)
    for arch in APT_ARCHES:
        pathlib.Path(dists_dir, "main", "binary-%s" % arch).mkdir(parents=True, exist_ok=True)

    _find_exec_cp(local_pkgs, "*.deb", apt_pool_dir)

    deb_count = _count(apt_pool_dir, "*.deb")
    log.info("APT: generating metadata for %s packages (packages served via R2)" % deb_count)

    # VACUITY FLOOR. dpkg-scanpackages over an EMPTY pool succeeds and writes a
    # valid, empty Packages file, so the repository publishes and `apt update`
    # reports no error -- it just offers nothing to install. DEFECT 2 is that
    # this exists for APT and for nothing else; DEFECT 3 is that a zero-padded
    # floor value turns it off.
    min_debs = os.environ.get("PKG_REPO_MIN_DEBS", "") or DEFAULT_MIN_DEBS
    if bash_lt(deb_count, min_debs):
        raise Refusal(
            1,
            "VACUOUS: %s holds %s .deb file(s), floor %s." % (apt_pool_dir, deb_count, min_debs),
            "Refusing to publish an APT repository that offers nothing to install.",
        )

    if dry_run:
        log.info("[DRY-RUN] Would generate APT repository metadata")
        return apt_dir, deb_count

    require_cmd("dpkg-scanpackages")

    for arch in APT_ARCHES:
        log.info("Generating Packages for %s..." % arch)
        packages = os.path.join(dists_dir, "main", "binary-%s" % arch, "Packages")
        with open(packages, "wb") as handle:
            _bare(
                ["dpkg-scanpackages", "--arch", arch, "pool/"],
                stdout=handle,
                cwd=apt_work_dir,
            )
        with open(packages + ".gz", "wb") as handle:
            _bare(["gzip", "-9c", packages], stdout=handle)

    log.info("Generating Release file...")
    release_date = _release_date()

    release = os.path.join(dists_dir, "Release")
    body = [
        "Origin: Rediacc",
        "Label: Rediacc CLI Repository",
        "Suite: stable",
        "Codename: stable",
        "Date: %s" % release_date,
        "Architectures: amd64 arm64",
        "Components: main",
        "Description: Rediacc CLI package repository",
        "MD5Sum:",
        *_checksum_rows(dists_dir, "md5"),
        "SHA256:",
        *_checksum_rows(dists_dir, "sha256"),
    ]
    with open(release, "w", encoding="utf-8") as handle:
        handle.write("\n".join(body) + "\n")

    log.info("Signing APT repository...")
    _gpg(
        gpg_opts,
        "--default-key",
        key_id,
        "--detach-sign",
        "--armor",
        "--output",
        os.path.join(dists_dir, "Release.gpg"),
        release,
    )
    _gpg(
        gpg_opts,
        "--default-key",
        key_id,
        "--clearsign",
        "--output",
        os.path.join(dists_dir, "InRelease"),
        release,
    )

    # `cp -r "$APT_WORK_DIR/pool" "$APT_DIR/pool"` -- the packages travel with
    # their metadata, which is what "self-contained" means here.
    _bare(["cp", "-r", os.path.join(apt_work_dir, "pool"), os.path.join(apt_dir, "pool")])

    log.info("APT repository built (self-contained with pool/)")
    return apt_dir, deb_count


def _phase5_rpm(
    local_pkgs: str, output_dir: str, channel: str, dry_run: bool, gpg_opts: list[str], key_id: str
) -> tuple[str, str]:
    """`:289-331`. Returns `(rpm_dir, rpm_count)`.

    TWO THINGS HAPPEN OUTSIDE THE DRY-RUN GUARD HERE, and both are DEFECT 4:
    the `.rpm` payload is copied into the output directory, and `rediacc.repo`
    is written. archlinux's equivalent config writer is INSIDE its guard.
    """
    log.step("Phase 5: Building RPM repository metadata")

    rpm_dir = os.path.join(output_dir, "rpm")
    pathlib.Path(rpm_dir).mkdir(parents=True, exist_ok=True)

    # DEFECT 4, first half: outside the guard, so `--dry-run` copies the payload.
    _find_exec_cp(local_pkgs, "*.rpm", rpm_dir)

    rpm_count = _count(rpm_dir, "*.rpm")
    log.info("RPM: generating metadata for %s packages (self-contained)" % rpm_count)

    if dry_run:
        log.info("[DRY-RUN] Would generate RPM repository metadata")
    else:
        require_cmd("createrepo_c")

        # Packages are in RPM_DIR alongside repodata/ -- no --baseurl needed.
        log.info("Running createrepo_c...")
        _bare(["createrepo_c", rpm_dir])

        log.info("Signing RPM repository...")
        _gpg(
            gpg_opts,
            "--default-key",
            key_id,
            "--detach-sign",
            "--armor",
            "--output",
            os.path.join(rpm_dir, "repodata", "repomd.xml.asc"),
            os.path.join(rpm_dir, "repodata", "repomd.xml"),
        )

        log.info("RPM repository built (self-contained with packages)")

    # DEFECT 4, second half: `:324-331` sits after the `fi`, so a preview writes
    # a real `.repo` file. `RELEASES_BASE_URL` is the one constants.sh value the
    # environment can override.
    base_url = os.environ.get("RELEASES_BASE_URL", "") or RELEASES_BASE_URL_DEFAULT
    with open(os.path.join(rpm_dir, "rediacc.repo"), "w", encoding="utf-8") as handle:
        handle.write(
            "[rediacc]\n"
            "name=Rediacc CLI Repository\n"
            "baseurl=%s/rpm/%s/\n"
            "enabled=1\n"
            "gpgcheck=1\n"
            "gpgkey=%s/rpm/%s/gpg.key\n" % (base_url, channel, base_url, channel)
        )
    return rpm_dir, rpm_count


def _apkindex_name(index_tarball: str) -> str:
    """`:389`. The first `P:`/`V:` pair in APKINDEX, as `<name>-<version>.apk`.

    DEFECT 1 LIVES HERE. `tar` is a subprocess whose non-zero status the twin
    propagates through `pipefail` into a bare `set -e` death, and the commonest
    way to reach that is the docker-less path two branches up, which has ALREADY
    printed "Docker not available, cannot generate APKINDEX" and believes it is
    continuing. `awk` always exits 0, so tar's status is the only one that can
    be non-zero.

    The awk program is reimplemented: `-F:`, remember the last `P:` field 2,
    print `name-<V field 2>.apk` at the first `V:` and stop.
    """
    try:
        proc = subprocess.run(
            ["tar", "xzf", index_tarball, "-O", "APKINDEX"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        raise Refusal(127) from None
    if proc.returncode != 0:
        raise Refusal(proc.returncode)
    name = ""
    for line in proc.stdout.decode("utf-8", errors="replace").split("\n"):
        fields = line.split(":")
        if line.startswith("P:"):
            name = fields[1] if len(fields) > 1 else ""
        elif line.startswith("V:"):
            return "%s-%s.apk" % (name, fields[1] if len(fields) > 1 else "")
    return ""


def _phase6_apk(
    local_pkgs: str, output_dir: str, dry_run: bool, cleanup_dirs: list[str]
) -> tuple[str, str]:
    """`:333-399`. Returns `(apk_dir, apk_count_total)`."""
    log.step("Phase 6: Building Alpine APK repository metadata")

    apk_dir = os.path.join(output_dir, "apk")
    apk_work_dir = tempfile.mkdtemp(prefix="tmp.")
    cleanup_dirs.append(apk_work_dir)

    for arch, nfpm_arch in APK_ARCHES:
        arch_work = os.path.join(apk_work_dir, arch)
        pathlib.Path(arch_work).mkdir(parents=True, exist_ok=True)
        _find_exec_cp(local_pkgs, "*-%s.apk" % nfpm_arch, arch_work, quiet=True)

    total = 0
    for arch, _nfpm in APK_ARCHES:
        total += int(_count(os.path.join(apk_work_dir, arch), "*.apk", quiet=True))
    apk_count_total = str(total)
    log.info("APK: generating metadata for %s packages (packages served via R2)" % apk_count_total)

    if dry_run:
        log.info("[DRY-RUN] Would generate APK repository metadata")
        return apk_dir, apk_count_total

    for arch, _nfpm in APK_ARCHES:
        arch_work = os.path.join(apk_work_dir, arch)
        arch_count = _count(arch_work, "*.apk", quiet=True)

        if arch_count == "0":
            log.warn("No APK packages found for %s, skipping" % arch)
            continue

        pathlib.Path(apk_dir, arch).mkdir(parents=True, exist_ok=True)

        log.info("Generating APKINDEX for %s (%s packages)..." % (arch, arch_count))
        if shutil.which("docker") is not None:
            _bare(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    "%s:/repo:ro" % arch_work,
                    "-v",
                    "%s:/out" % os.path.join(apk_dir, arch),
                    "alpine:latest",
                    "sh",
                    "-c",
                    "apk index --allow-untrusted -o /out/APKINDEX.tar.gz /repo/*.apk",
                ]
            )
        else:
            log.warn("Docker not available, cannot generate APKINDEX for %s" % arch)

        # Copy packages to output, renamed to match APKINDEX expectations.
        # DEFECT 1 fires on the FIRST iteration of this loop when the branch
        # above took the warning arm. DEFECT 7 fires when it did not and there
        # is more than one file: `apk_name` is recomputed from the SAME index
        # every time and always yields the same string, so each file overwrites
        # the last and the repository ships one package where two were built.
        for apk_file in sorted(globmod.glob(os.path.join(arch_work, "*.apk"))):
            if not pathlib.Path(apk_file).is_file():
                continue
            apk_name = _apkindex_name(os.path.join(apk_dir, arch, "APKINDEX.tar.gz"))
            if apk_name:
                shutil.copy(apk_file, os.path.join(apk_dir, arch, apk_name))
            else:
                shutil.copy(apk_file, os.path.join(apk_dir, arch))

    log.info("APK repository built (self-contained with packages)")
    return apk_dir, apk_count_total


def _phase7_archlinux(
    local_pkgs: str, output_dir: str, channel: str, dry_run: bool, cleanup_dirs: list[str]
) -> tuple[str, str]:
    """`:401-458`. Returns `(archlinux_dir, arch_count_total)`."""
    log.step("Phase 7: Building Arch Linux repository metadata")

    archlinux_dir = os.path.join(output_dir, "archlinux")
    work_dir = tempfile.mkdtemp(prefix="tmp.")
    cleanup_dirs.append(work_dir)

    for arch in ARCHLINUX_ARCHES:
        arch_work = os.path.join(work_dir, arch)
        pathlib.Path(arch_work).mkdir(parents=True, exist_ok=True)
        _find_exec_cp(local_pkgs, "*-%s.pkg.tar.zst" % arch, arch_work, quiet=True)

    total = 0
    for arch in ARCHLINUX_ARCHES:
        total += int(_count(os.path.join(work_dir, arch), "*.pkg.tar.zst", quiet=True))
    arch_count_total = str(total)
    log.info(
        "Archlinux: generating metadata for %s packages (packages served via R2)" % arch_count_total
    )

    if dry_run:
        log.info("[DRY-RUN] Would generate Archlinux repository metadata")
        return archlinux_dir, arch_count_total

    for arch in ARCHLINUX_ARCHES:
        arch_work = os.path.join(work_dir, arch)
        arch_count = _count(arch_work, "*.pkg.tar.zst", quiet=True)

        if arch_count == "0":
            log.warn("No Archlinux packages found for %s, skipping" % arch)
            continue

        pathlib.Path(archlinux_dir, arch).mkdir(parents=True, exist_ok=True)

        log.info("Generating pacman database for %s (%s packages)..." % (arch, arch_count))
        if shutil.which("docker") is not None:
            _bare(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    "%s:/repo" % arch_work,
                    "-v",
                    "%s:/out" % os.path.join(archlinux_dir, arch),
                    "archlinux:latest",
                    "bash",
                    "-c",
                    (
                        "cp /repo/*.pkg.tar.zst /out/ 2>/dev/null; "
                        "repo-add /out/rediacc.db.tar.gz /out/*.pkg.tar.zst 2>/dev/null"
                    ),
                ]
            )
        else:
            log.warn("Docker not available, cannot generate pacman database for %s" % arch)

    # `:451`. INSIDE the guard, unlike `rediacc.repo`. That asymmetry is DEFECT
    # 4. `\\$arch` in the heredoc is escaped, so pacman -- not this script --
    # expands it.
    base_url = os.environ.get("RELEASES_BASE_URL", "") or RELEASES_BASE_URL_DEFAULT
    with open(os.path.join(archlinux_dir, "rediacc.conf"), "w", encoding="utf-8") as handle:
        handle.write(
            "[rediacc]\n"
            "SigLevel = Optional TrustAll\n"
            "Server = %s/archlinux/%s/$arch\n" % (base_url, channel)
        )

    log.info("Archlinux repository metadata built")
    return archlinux_dir, arch_count_total


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def build(argv: list[str]) -> int:
    """The twin, top to bottom, in its order.

    Deliberately NOT decomposed further than one function per PHASE: the phases
    are the twin's own headings and appear in its output, while anything finer
    would invent a structure a reader diffing the two files cannot follow.
    """
    source_common()

    values, dry_run, wants_help = parse_args(argv)
    if wants_help:
        print(
            "Usage: %s --version VER --local-pkgs DIR --output DIR --channel CHANNEL [--dry-run]"
            % sys.argv[0],
            flush=True,
        )
        return 0

    # `:74-90`. The FIRST missing one wins; the twin exits rather than collecting.
    for name, flag in (
        ("VERSION", "--version"),
        ("LOCAL_PKGS", "--local-pkgs"),
        ("OUTPUT_DIR", "--output"),
        ("CHANNEL", "--channel"),
    ):
        if not values[name]:
            raise Refusal(1, "Missing required argument: %s" % flag)

    version = values["VERSION"]
    local_pkgs = values["LOCAL_PKGS"]
    output_dir = values["OUTPUT_DIR"]
    channel = values["CHANNEL"]

    require_dir(local_pkgs)

    # `$(cd X && pwd)` is bash's LOGICAL pwd, which normalises `..` lexically and
    # does NOT resolve symlinks. `os.path.abspath` is that, exactly;
    # `Path.resolve()` would be `pwd -P` and would print a different path for a
    # symlinked output directory.
    local_pkgs = os.path.abspath(local_pkgs)
    pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_dir = os.path.abspath(output_dir)

    log.step("Building package repositories")
    log.info("  Version: %s" % version)
    log.info("  Local packages: %s" % local_pkgs)
    log.info("  Output: %s" % output_dir)
    log.info("  Channel: %s" % channel)

    # `:110-112`. The EXIT trap is armed BEFORE anything is added to the list, so
    # a refusal in phase 1 still runs `rm -rf` over an empty array. Harmless in
    # bash 5 and harmless here; recorded because an empty-array expansion under
    # `set -u` is the kind of thing that used to be fatal.
    cleanup_dirs: list[str] = []
    try:
        return _phases(version, local_pkgs, output_dir, channel, dry_run, cleanup_dirs)
    finally:
        for path in cleanup_dirs:
            shutil.rmtree(path, ignore_errors=True)


def _phases(
    version: str,
    local_pkgs: str,
    output_dir: str,
    channel: str,
    dry_run: bool,
    cleanup_dirs: list[str],
) -> int:
    """`:105-468`, everything the EXIT trap is responsible for cleaning up after.

    Split from `build()` for one reason: `trap cleanup EXIT` fires on every path
    from `:112` onward, and a `finally` around a CALL expresses that where a
    `finally` wrapped around half a function body does not. `version` is unused
    past the banner, exactly as in the twin, and is kept in the signature so a
    reader does not go looking for where it went.
    """
    del version  # the twin logs it and never reads it again

    gpg_opts = ["--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback"]
    passphrase = os.environ.get("RELEASE_GPG_PASSPHRASE", "")
    if passphrase:
        # STDOUT, and it is the only thing besides `--help` that goes there.
        print("::add-mask::%s" % passphrase, flush=True)
        gpg_opts += ["--passphrase", passphrase]

    key_id = _phase1_gpg(output_dir, dry_run, gpg_opts, cleanup_dirs)

    # Historical versions: not downloaded. Each channel is self-contained with
    # only the current version; previous versions accumulate via s3 sync.

    apt_dir, deb_count = _phase4_apt(
        local_pkgs, output_dir, dry_run, gpg_opts, key_id, cleanup_dirs
    )
    rpm_dir, rpm_count = _phase5_rpm(local_pkgs, output_dir, channel, dry_run, gpg_opts, key_id)
    apk_dir, apk_count = _phase6_apk(local_pkgs, output_dir, dry_run, cleanup_dirs)
    archlinux_dir, arch_count = _phase7_archlinux(
        local_pkgs, output_dir, channel, dry_run, cleanup_dirs
    )

    log.step("Package repository build complete (metadata only)")
    log.info("  APT: %s/ (metadata for %s .deb packages)" % (apt_dir, deb_count))
    log.info("  RPM: %s/ (metadata for %s .rpm packages)" % (rpm_dir, rpm_count))
    log.info("  APK: %s/ (metadata for %s .apk packages)" % (apk_dir, apk_count))
    log.info(
        "  Archlinux: %s/ (metadata for %s .pkg.tar.zst packages)" % (archlinux_dir, arch_count)
    )
    log.info("  Packages are served from Cloudflare R2")
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
