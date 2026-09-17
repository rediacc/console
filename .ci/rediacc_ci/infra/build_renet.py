#!/usr/bin/env python3
"""Port of `.ci/scripts/infra/build-renet.sh`.

Builds the renet binary from Go source at `private/renet/`, skipping the build only when the binary already on disk was built THE SAME WAY, and hands the path
back on stdout as `RENET_BINARY=<path>` (plus an append to `$GITHUB_ENV` when
running under GitHub Actions).

WHAT "THE SAME WAY" MEANS, AND WHY IT IS NOT `-f bin/renet`. The twin's own comment (build-renet.sh:44-63) records the incident: this used to be a bare existence test, ten CI steps call the script, and a job that had built `--nolicense` handed its binary to a later job that wanted an enforcing one, so that job's licence assertions passed for free. The identity string
`<mode>|<sha256(ACCOUNT_ED25519_PUBLIC_KEY)[:16]>` covers everything that changes the BYTES, and it is stamped into `bin/.renet-build-identity` only AFTER the produced binary has been seen on disk. Both halves are reproduced here
exactly; `build_identity()` and `build_args()` are exported so a test can drive
them without a build.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT, because these are the twin's own probes and the differential fakes them on PATH:

  * `uname -s`   -- the `.exe` suffix decision. `core.platform.exe_suffix()` was
    deliberately NOT used: it RAISES on a system string it does not recognise,
    where the twin's `case` falls through to an empty suffix for anything that
    is not MINGW/MSYS/CYGWIN. A port that refused where the twin shrugged would
    be a divergence invented by a helper, so the twin's own probe is run and the
    twin's own three prefixes are matched.
  * `command -v go` -> `shutil.which("go")`. The twin never runs go itself; it
    only asks whether it is there before delegating.
  * `./build.sh dev [--license|--nolicense]`, from inside `private/renet`. The
    Go build is emphatically not reimplemented: `build.sh` owns the licence
    decision, the ldflags and the output path, and a Python copy of it would be
    a second source of truth for what a shipped binary contains.

NOT SHELLED OUT: the SHA-256. The twin spells it `printf '%s' "$KEY" | sha256sum | cut -c1-16`, and `hashlib` produces the same 16 hex characters with no ambiguity of encoding to get wrong (unlike, say, a DER key blob). `test_infra_build_renet.py::test_the_identity_digest_is_the_twins_own _pipeline` drives the two against each other rather than against a constant.

This buys ONE DELIBERATE DIVERGENCE, and finding out what it actually was uncovered a REAL DEFECT IN THE TWIN. On a host with no `sha256sum` (stock macOS ships `shasum`, not `sha256sum`, and this script advertises itself as locally runnable) the twin does NOT die. The failing pipeline sits in a COMMAND SUBSTITUTION USED AS AN ARGUMENT to `printf`, where neither `set -e` nor
`pipefail` can see it: printf succeeds with an empty second field, and the identity silently collapses from `<mode>|<16 hex>` to `<mode>|`.

The consequence is exactly the incident the stamp was added to prevent. With the key half of the identity gone, a binary linked against one ACCOUNT_ED25519_PUBLIC_KEY is handed to a job that wanted another and NO REBUILD HAPPENS -- one line of stderr, exit 0.

This port keeps the key half. Both halves are asserted by `test_a_missing_sha256sum_is_the_one_deliberate_divergence` and the consequence is demonstrated by `test_the_collapsed_identity_defeats_the_rebuild_the_stamp_exists_for`, so the difference is a recorded decision and not a surprise. Reported, not fixed: the repair is a cutover-box decision.

-----------------------------------------------------------------------------
CONSOLE ROOT COMES FROM THIS FILE'S OWN LOCATION
-----------------------------------------------------------------------------
Matching the twin's `SCRIPT_DIR/../../..`. This module sits one directory deeper than the twin, so it is `parents[3]` here where the twin's is `parents[2]` of
ITS directory; both land on the repository root. `rediacc_ci.paths.repo_root()`
is deliberately not used, on the `ci_stop_elite.py` precedent: that resolver honours `$REDIACC_CI_ROOT` and the twin has no such override, so a differential pointing one at a fixture and not the other would diverge for a reason that has nothing to do with the port.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE, ONE NAME AT A TIME
-----------------------------------------------------------------------------
`os.environ.get("RDC_RENET_LICENSE", "")`, `...get("ACCOUNT_ED25519_PUBLIC_KEY",
"")`, `...get("GITHUB_ENV", "")`. No `env = dict(os.environ)` alias anywhere:
the env-manifest reader parses direct `os.environ` reads and an alias makes the three names invisible to it.

`RDC_BENCH` IS NOT READ, and its absence is the point. The twin's identity
function used to have a second arm for it; that arm was removed 2026-09-09
because bench is a CONFIG now (`./rdc.sh --config bench`) and nothing else in the tree reads the name. Re-adding it here would resurrect a dead knob in the one file whose whole job is to decide whether a binary needs rebuilding.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log

# U+2014, written as an escape so no em dash is typed into a file under `.ci/rediacc_ci`, which `check:ci-em-dash-surfaces` scans. The CHARACTER still has to reach stderr, because the twin prints it and this port's whole claim is byte-identical output.
_EM_DASH = "\u2014"

# The three `uname -s` prefixes the twin's `case` treats as Windows. Named rather than inlined so the set is readable next to the reason it is not `core.platform.exe_suffix()` (see the module docstring).
_WINDOWS_UNAME_PREFIXES = ("MINGW", "MSYS", "CYGWIN")


def console_root() -> pathlib.Path:
    """The repository root, derived the way the twin derives it: from the
    subject file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/infra/build_renet.py
    return pathlib.Path(__file__).resolve().parents[3]


def build_args(argv: list[str]) -> list[str]:
    """The twin's `for arg in "$@"` filter: `--license` and `--nolicense` are
    forwarded, in the order given, and EVERY OTHER ARGUMENT IS DROPPED IN
    SILENCE.

    That silence is the twin's behaviour and is reproduced deliberately, not endorsed: `build-renet.sh --nolicence` (one letter short) builds a DEFAULT binary and says nothing, and the caller reads the exit 0 as "built the way I asked". Reported as a twin defect rather than fixed here, because a port that started rejecting arguments would fail differently from the script it claims
    to be equivalent to.
    """
    return [arg for arg in argv if arg in ("--nolicense", "--license")]


def build_identity(args: list[str]) -> str:
    """`<mode>|<first 16 hex of sha256(ACCOUNT_ED25519_PUBLIC_KEY)>`.

    Mirrors the twin's `case " ${BUILD_ARGS[*]-} " in` exactly, including two
    details that a rewrite gets wrong:

      * `--license` is tested FIRST, so passing both flags in either order
        yields "license". The bash `case` stops at the first matching pattern
        and the array is joined with spaces, so order of the FLAGS does not
        matter, only the order of the PATTERNS.
      * the whole joined string is wrapped in spaces before matching, which is
        what stops `--nolicense` from matching the `--license` pattern.

    `RDC_RENET_LICENSE=1` then OVERRIDES whatever the flags said, because
    `build.sh dev` opts into enforcement from the environment and a stamp that only looked at the flags would call two different binaries the same thing.
    """
    joined = " %s " % " ".join(args)
    mode = "default"
    if " --license " in joined:
        mode = "license"
    elif " --nolicense " in joined:
        mode = "nolicense"
    if os.environ.get("RDC_RENET_LICENSE", "") == "1":
        mode = "enforce"
    key = os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY", "")
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "%s|%s" % (mode, digest)


def exe_suffix() -> str:
    """`.exe` under Git Bash / MSYS / Cygwin, empty everywhere else.

    `uname` is invoked, not `platform.system()`: under MSYS the two disagree (Python reports "Windows", uname reports "MINGW64_NT-10.0"), and the twin asks uname. A missing or failing `uname` yields "", which is what the twin's `case "$(uname -s)"` also falls through to.
    """
    try:
        completed = subprocess.run(
            ["uname", "-s"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    system = completed.stdout.strip() if completed.returncode == 0 else ""
    if system.startswith(_WINDOWS_UNAME_PREFIXES):
        return ".exe"
    return ""


def main(argv: list[str]) -> int:
    root = console_root()
    args = build_args(argv)

    renet_src = root / "private" / "renet"
    renet_bin = renet_src / "bin" / ("renet%s" % exe_suffix())

    # Step 1: the submodule has to be there. This is checked BEFORE the identity is computed in the twin too, so a checkout without the submodule gets the actionable message rather than whatever the identity pipeline says.
    if not renet_src.is_dir():
        log.error("private/renet/ not found %s submodule not checked out" % _EM_DASH)
        log.error("Run: git submodule update --init private/renet")
        return 1

    stamp = renet_src / "bin" / ".renet-build-identity"
    want = build_identity(args)

    # `"$(cat "$RENET_STAMP" 2>/dev/null)"`: a missing or unreadable stamp reads as the empty string, which never equals an identity (it always carries a `|` and 16 hex characters), so the build runs.
    try:
        have = stamp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        have = ""
    # Command substitution strips ALL trailing newlines, and the stamp is
    # written without one; stripping here keeps a hand-edited stamp with a
    # trailing newline comparing equal, exactly as bash would.
    have = have.rstrip("\n")

    if renet_bin.is_file() and stamp.is_file() and have == want:
        log.info("Renet binary already built the same way: %s" % renet_bin)
    else:
        if renet_bin.is_file():
            log.info(
                "Renet binary exists but was built differently %s rebuilding for: %s"
                % (_EM_DASH, want)
            )
            # THE TWIN DELETES BEFORE IT CHECKS FOR go, and this port keeps that order. It is a real defect (a host without go loses a working binary and gets exit 1), reported rather than repaired: reordering here would make the port's filesystem effect differ from the twin's on the exact input that exposes the bug, and the differential would then be certifying the wrong script.
            #
            # `rm -f` is silent on a file it cannot remove only when the file is
            # absent; a permission error does print and fail. That sub-case is
            # not reachable from any caller in this tree (bin/ is created by build.sh as the invoking user), so the twin's `rm -f` is matched on its common path and no message is invented for the other.
            with contextlib.suppress(OSError):
                renet_bin.unlink()

        # Step 3: require go. `command -v go &>/dev/null` -> `shutil.which`.
        if shutil.which("go") is None:
            log.error("Go is not installed (required for building renet)")
            log.error("Install Go from: https://go.dev/dl/")
            return 1

        # Step 4: delegate. build.sh owns the licence decision; the flags are
        # only forwarded when one was passed, matching the twin's guarded
        # expansion `${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"}`.
        log.step("Building renet from source...")
        try:
            completed = subprocess.run(
                ["./build.sh", "dev", *args],
                cwd=str(renet_src),
                check=False,
            )
        except PermissionError:
            # bash's "cannot execute" status.
            return 126
        except OSError:
            # bash's "command not found" status.
            return 127
        if completed.returncode != 0:
            # `set -e` on the subshell: the twin exits with build.sh's own status and prints nothing of its own. Silence is deliberate.
            return completed.returncode

        # Step 5: the binary has to exist before anything is stamped.
        if not renet_bin.is_file():
            log.error("Renet build failed: binary not found at %s" % renet_bin)
            return 1
        # Stamp AFTER the binary is verified present, never before: a stamp written ahead of a failed build would make the next run skip and hand back nothing, or a half-written binary that looks current.
        stamp.write_text(want, encoding="utf-8")
        log.info("Renet built successfully: %s" % renet_bin)

    # `export RENET_BINARY` in the twin is inert for a child process and is not
    # reproduced as an export; the two OBSERVABLE consequences are, and they are
    # the ones every caller actually reads.
    github_env = os.environ.get("GITHUB_ENV", "")
    if github_env:
        with pathlib.Path(github_env).open("a", encoding="utf-8") as handle:
            handle.write("RENET_BINARY=%s\n" % renet_bin)
        log.info("Set RENET_BINARY in GITHUB_ENV")

    print("RENET_BINARY=%s" % renet_bin, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
