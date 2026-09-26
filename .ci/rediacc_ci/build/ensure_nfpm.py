#!/usr/bin/env python3
"""Port of `.ci/scripts/build/ensure-nfpm.sh` (74 lines).

Install the pinned `nfpm` if it is not already usable, and print the directory holding it. Idempotent: a second run downloads nothing. The twin's own header carries WHY it exists (two copies of the six install lines had already drifted, so the checksum was verified on one of the two installs and not the other) and that reasoning is not restated here.

LIVE CALLERS, none repointed by this port:
  * `.github/workflows/ci.yml:880`      `ensure-nfpm.sh >>"$GITHUB_PATH"`
  * `.github/workflows/cd-stage.yml:151` the same, in the staging job
  * `.ci/scripts/test/test-linux-packages.sh:18`  `PATH="$(...):$PATH"`
  * `.ci/scripts/test/proxies/proxy-linux-packages.sh:47`
  * `.ci/scripts/test/proxies/proxy-ensure-nfpm.sh`, the REGISTERED gate
    `check:ci-proxy-ensure-nfpm` (`package.json:392`,
    `scripts/ci-runner/manifest.ts:7496-7499`), which runs the twin against a
    throwaway fixture root with a cold cache.

-----------------------------------------------------------------------------
WHY THE EXTERNAL BINARIES ARE CALLED RATHER THAN REIMPLEMENTED
-----------------------------------------------------------------------------
`curl`, `sha256sum` and `tar` are invoked as subprocesses, exactly as the twin invokes them, and their stderr is INHERITED. Two reasons, both of them things a differential would otherwise catch as a divergence:

  * THE EXIT CODE IS THE CONTRACT. `set -e` in the twin means the script exits
    with curl's 22, or sha256sum's 1, or tar's 2. `hashlib.sha256` and
    `urllib.request` produce Python exceptions with none of those numbers, and
    every caller above reads only the exit status and the printed directory.
  * THE DIAGNOSTIC TEXT IS THE CONTRACT TOO. On a mismatch the twin's only
    output is GNU coreutils' own `sha256sum: WARNING: 1 computed checksum did
    NOT match`, because the `<file>: FAILED` line goes to the stdout the twin
    redirects to /dev/null. Forging that sentence in Python would drift the day
    coreutils rewords it.

-----------------------------------------------------------------------------
THE PIN IS READ BY SOURCING `constants.sh`, NOT BY PARSING IT
-----------------------------------------------------------------------------
`.ci/config/constants.sh` is a bash program, not a KEY=value table: it re-sources
`.devcontainer/toolchain.env` under `set -a` (constants.sh:20-32), guards against double-sourcing with `REDIACC_CONSTANTS_LOADED`, and `return 1`s with a message on stderr when the pins file is unreadable. A regex reader would silently disagree
with all three. So this port runs the same `source` in a bash child with BOTH
STREAMS INHERITED and collects the two values over a side channel (a temp file), which reproduces:

  * a missing `.devcontainer/toolchain.env` printing
    `constants.sh: gate toolchain pins missing: <path>` on stderr and exiting 1
    (constants.sh:30-31 plus the twin's `set -e` on a failed `source`),
  * anything constants.sh may ever print on stdout landing on the caller's
    stdout, which matters because every caller substitutes this script's stdout
    straight into `PATH`.

`.devcontainer/toolchain.env` is resolved by constants.sh from ITS OWN location, so a fixture root gets the fixture's pins; nothing here passes a path.

-----------------------------------------------------------------------------
THE REPO ROOT IS THIS FILE'S OWN LOCATION, and `paths.repo_root()` is NOT used
-----------------------------------------------------------------------------
Same call as `rediacc_ci.infra.ci_start_elite._console_root`: `paths.repo_root()` honours `$REDIACC_CI_ROOT` and the twin has no such override, so a fixture that pointed one side at a tree and not the other would diverge silently. The twin's `SCRIPT_DIR/../../..` from `.ci/scripts/build/` is `parents[3]` of this file's directory chain, since this module sits one level deeper.

One named, unreproducible difference: the twin's `cd "$(dirname ...)" && pwd` resolves symlinks in the DIRECTORY only, while `Path.resolve()` also resolves a symlinked file. Reaching this file through a symlink is not something any caller does, and the alternative (`os.path.abspath`) is the spelling `rediacc_ci.paths`' own docstring calls out as differently wrong.

-----------------------------------------------------------------------------
TWO REAL DEFECTS IN THE TWIN, REPRODUCED HERE RATHER THAN FIXED
-----------------------------------------------------------------------------
Fixing either would change a live gate's and two workflows' behaviour, which is outside this port's ownership. Both are pinned by tests in `.ci/rediacc_ci/tests/test_build_ensure_nfpm.py`.

  1. A WARM CACHE IS NEVER CHECKED AGAINST THE PIN (`ensure-nfpm.sh:42-45`).
     The cached-binary branch tests only that `$BIN_DIR/nfpm --version` exits 0;
     it never compares the reported version to `$NFPM_VERSION`. So bumping the
     pin in `constants.sh` does not invalidate an existing `.ci/cache/bin/nfpm`,
     and every later run keeps handing out the OLD binary while the pin site
     says otherwise. Measured, not estimated: with a fixture whose `constants.sh`
     pins 2.45.0 and whose `.ci/cache/bin/nfpm` reports 1.0.0-stale, the twin
     exits 0 and prints the cache directory, downloading nothing.
     Blast radius: 2 of the 5 live callers are affected and 3 are not. CI and
     cd-stage check out fresh runners with no `.ci/cache/` (`.gitignore:143`,
     and nothing in either workflow restores it), so those two always take the
     cold path. `test-linux-packages.sh:18` and `proxy-linux-packages.sh:47`
     both run against the real repo root and therefore against the warm cache.
     The gate that exists to catch pin drift, `proxy-ensure-nfpm.sh`, cannot see
     it by construction: it builds a throwaway fixture root precisely so the
     cache is cold (`proxy-ensure-nfpm.sh:13-21`).
  2. AN `nfpm` ANYWHERE ON `PATH` WINS OVER THE PIN (`ensure-nfpm.sh:38-41`).
     Same shape, one rung earlier and with a wider door: any working `nfpm` on
     `PATH`, at any version, short-circuits the whole pin. `proxy-ensure-nfpm.sh`
     :81-87 strips it from `PATH` for its own run, which is an acknowledgement
     of the branch rather than a check of it.

-----------------------------------------------------------------------------
ONE NAMED DIVERGENCE THAT IS NOT REPRODUCED
-----------------------------------------------------------------------------
When `constants.sh` sources cleanly but defines no `NFPM_VERSION`, the twin dies at `:54` with bash's own `line 54: NFPM_VERSION: unbound variable`, an internal diagnostic carrying the interpreter's path and line number. That is not a sentence a second language can produce, and `scripts/lib/shadow-gate.ts` files it as CHATTER on both sides (no `::error::`/`✗`/`ERROR:` marker), so
it plays no part in any recorded verdict. The port exits 1 with the same empty stdout and does not forge the text. Pinned by `test_unpinned_version_exits_1_without_forging_bash_text`.

K=5 LEDGER: `.ci/shadow/w7p6-ensure-nfpm.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

# `.ci/scripts/build/ensure-nfpm.sh:26-27` resolves <root> as SCRIPT_DIR/../../..
# from `.ci/scripts/build/`; this module is one directory deeper.
_ROOT_PARENT_INDEX = 3

# `.ci/scripts/build/ensure-nfpm.sh:32`.
_BIN_RELPATH = (".ci", "cache", "bin")

# `.ci/scripts/build/ensure-nfpm.sh:30`.
_CONSTANTS_RELPATH = (".ci", "config", "constants.sh")

# The two names read out of constants.sh (`:54-55`). Named rather than inlined so a test can assert the twin still reads exactly these.
VERSION_KEY = "NFPM_VERSION"
SHA_KEY = "NFPM_SHA256_LINUX_X86_64"

# `.ci/scripts/build/ensure-nfpm.sh:52-53`. The twin's case arm, verbatim.
PINNED_ARCHES = ("x86_64", "amd64")


def repo_root() -> pathlib.Path:
    """The twin's `REPO_ROOT`. See the module docstring on why not `paths`."""
    return pathlib.Path(__file__).resolve().parents[_ROOT_PARENT_INDEX]


def bin_dir(root: pathlib.Path) -> pathlib.Path:
    """`BIN_DIR="$REPO_ROOT/.ci/cache/bin"` (:32)."""
    return root.joinpath(*_BIN_RELPATH)


def tarball_name(version: str) -> str:
    """`nfpm_${NFPM_VERSION}_Linux_x86_64.tar.gz` (:54)."""
    return "nfpm_%s_Linux_x86_64.tar.gz" % version


def download_url(version: str, tarball: str) -> str:
    """`:65`, verbatim. Exported so a test can assert the host and the `v` prefix."""
    return "https://github.com/goreleaser/nfpm/releases/download/v%s/%s" % (version, tarball)


def is_pinned_arch(arch: str) -> bool:
    """`case "$ARCH" in x86_64 | amd64)` (:52-53)."""
    return arch in PINNED_ARCHES


def unpinned_arch_message(arch: str) -> str:
    """`:58`, verbatim, minus the trailing newline `echo` adds."""
    return (
        "ensure-nfpm: no pinned checksum for %s in .ci/config/constants.sh -- "
        "add one rather than downloading unverified bytes" % arch
    )


def fetching_message(version: str, arch: str) -> str:
    """`:66`, verbatim, minus the trailing newline `echo` adds."""
    return "ensure-nfpm: fetching nfpm %s for %s" % (version, arch)


def _binary_answers(binary: str | pathlib.Path) -> bool:
    """`"$BIN_DIR/nfpm" --version >/dev/null 2>&1` -- ask the binary, not the file.

    The twin's own comment (:34-37) is the reason this is not a `-x` test alone: a truncated download and an interrupted extraction both leave a path `test -x` is happy with.
    """
    try:
        return (
            subprocess.run(
                [str(binary), "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
            == 0
        )
    except OSError:
        # `command -v` found it and exec then failed (a text-file-busy, a bad interpreter line). Bash's `if` treats a failed exec as a false condition and falls through to the next branch; so does this.
        return False


def machine_arch() -> tuple[int, str]:
    """`ARCH="$(uname -m)"` (:51). Returns (rc, arch).

    `uname` IS RESOLVED THROUGH `PATH`, NOT `os.uname()`, and the difference is load-bearing rather than pedantic. The REGISTERED gate `.ci/scripts/test/proxies/proxy-ensure-nfpm.sh:149-158` drives the unpinned-architecture refusal by putting a `uname` shim on `PATH` that answers `riscv64` -- "a real execution of the branch rather than a claim about it", in its own words.
    `os.uname()` is a raw syscall that no shim can reach, so a port spelled that way would take the x86_64 arm under the gate's refusal case and try to download instead of refusing.

    Command substitution strips TRAILING newlines and inherits stderr; a failing `uname` makes the assignment itself fail, which under `set -e` exits with uname's own status.
    """
    proc = subprocess.run(["uname", "-m"], stdout=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0:
        return proc.returncode, ""
    return 0, proc.stdout.rstrip("\n")


def read_pins(constants: pathlib.Path) -> tuple[int, str, str]:
    """`source "$REPO_ROOT/.ci/config/constants.sh"` (:30). Returns (rc, version, sha).

    BOTH STREAMS ARE INHERITED, so constants.sh's own stderr (`:30-31`, the missing-pins refusal) reaches the caller exactly as it does under the twin's `source`. A non-zero rc is the twin's `set -e` firing on a failed source.
    """
    with tempfile.TemporaryDirectory() as sidechannel:
        out = pathlib.Path(sidechannel) / "pins"
        # `%s` below is printf's, not Python's: the two values are interpolated as SHELL parameter expansions, one per line, so a value containing a `%` cannot re-enter either formatter. Concatenated rather than `%`-formatted for exactly that reason.
        body = (
            "set -euo pipefail\n"
            'source "$1"\n'
            'printf "%s\\n%s\\n" "${' + VERSION_KEY + '-}" "${' + SHA_KEY + '-}" >"$2"\n'
        )
        proc = subprocess.run(
            ["bash", "-c", body, "bash", str(constants), str(out)],
            check=False,
        )
        if proc.returncode != 0:
            return proc.returncode, "", ""
        try:
            fields = out.read_text(encoding="utf-8").split("\n")
        except OSError:
            return 1, "", ""
    return 0, fields[0], fields[1] if len(fields) > 1 else ""


def run(argv: list[str]) -> int:
    """The twin's whole body, in its order. Extra arguments are ignored, as there."""
    del argv  # `.ci/scripts/build/ensure-nfpm.sh` parses none.
    root = repo_root()

    rc, version, want = read_pins(root.joinpath(*_CONSTANTS_RELPATH))
    if rc != 0:
        return rc

    cache = bin_dir(root)

    # :38-41. An nfpm anywhere on PATH wins over the pin. See defect 2.
    on_path = shutil.which("nfpm")
    if on_path is not None and _binary_answers(on_path):
        print(os.path.dirname(on_path))
        return 0

    # :42-45. A warm cache is never checked against the pin. See defect 1.
    cached = cache / "nfpm"
    if os.access(str(cached), os.X_OK) and _binary_answers(cached):
        print(str(cache))
        return 0

    # :51-61.
    rc, arch = machine_arch()
    if rc != 0:
        return rc
    if not is_pinned_arch(arch):
        print(unpinned_arch_message(arch), file=sys.stderr)
        return 1

    if not version or not want:
        # The `set -u` abort at :54-55. See the module docstring: the text is bash-internal and deliberately not forged.
        return 1

    tarball = tarball_name(version)
    tmp = tempfile.mkdtemp()
    try:
        url = download_url(version, tarball)
        # :66. stderr, before the network call, so a hung fetch still says what it is hung on.
        print(fetching_message(version, arch), file=sys.stderr, flush=True)
        archive = os.path.join(tmp, tarball)
        rc = subprocess.run(
            [
                "curl",
                "-sfL",
                "--retry",
                "3",
                "--retry-delay",
                "2",
                "--retry-all-errors",
                "-o",
                archive,
                url,
            ],
            check=False,
        ).returncode
        if rc != 0:
            return rc

        # :70. VERIFY BEFORE EXTRACTING. stdout to /dev/null (that is where the `<file>: FAILED` line goes); stderr inherited (that is where the WARNING goes).
        rc = subprocess.run(
            ["sha256sum", "-c", "-"],
            input="%s  %s\n" % (want, archive),
            text=True,
            stdout=subprocess.DEVNULL,
            check=False,
        ).returncode
        if rc != 0:
            return rc

        # :71-73. Only now does the cache directory come into existence.
        cache.mkdir(parents=True, exist_ok=True)
        rc = subprocess.run(
            ["tar", "xzf", archive, "-C", str(cache), "nfpm"],
            check=False,
        ).returncode
        if rc != 0:
            return rc
        # `chmod +x "$BIN_DIR/nfpm"` (:73). Bare `+x` is `a+x` MASKED BY UMASK, not a flat 0755: it adds execute where the umask permits and touches no other bit, so a tar member that arrived 0644 becomes 0755 under the usual 022 while one that arrived 0600 becomes 0700. Writing 0o755 here would ADD group and world READ on that second file, which the twin never does. `os.umask` has
        # no reader, so it is set-and-restored.
        mask = os.umask(0)
        os.umask(mask)
        os.chmod(str(cached), os.stat(str(cached)).st_mode | (0o111 & ~mask))
    finally:
        # `trap 'rm -rf "$TMP"' EXIT` (:64).
        shutil.rmtree(tmp, ignore_errors=True)

    print(str(cache))
    return 0


def main(argv: list[str]) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
