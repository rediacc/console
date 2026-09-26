#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-cli.sh`.

Builds the CLI workspace, optionally bundles it into a single file, and optionally verifies that the build left something behind. Six live call sites, all of them workflow steps: `.github/workflows/ci-build-docker.yml:69` and five in `.github/workflows/ct-tests.yml` (356, 518, 673, 832, 988). Every one of them invokes it bare, with no arguments, so the default path -- bundle AND
verify -- is the only path CI exercises.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT, with streams inherited so the build's own output reaches the workflow log unchanged:

  * `npm run build:cli` (root script: `npm run build -w @rediacc/cli`, which is
    `tsc` behind a `prebuild` that embeds templates).
  * `npm run build:bundle -w @rediacc/cli` (`node bundle.mjs`).
  * `ls -lah packages/cli/dist/`. NOT reimplemented. Its output is a human
    listing whose exact column layout, size suffixes and date format belong to
    coreutils; a Python rewrite would produce something that looks like `ls` and
    is not, in the one place a reader goes when a build looks wrong.

NOT SHELLED OUT: the two existence tests, which are `[[ -d ]]` and `[[ -f ]]`.

-----------------------------------------------------------------------------
DEFECT 1, REPRODUCED AND NOT FIXED: THE ARGUMENT PARSER HAS NO `*)` ARM
-----------------------------------------------------------------------------
    for arg in "$@"; do
        case "$arg" in
            --no-bundle) BUNDLE=false ;;
            --no-verify) VERIFY=false ;;
            --bundle) BUNDLE=true ;;
            --verify) VERIFY=true ;;
        esac
    done

Anything else is silently accepted, and the script proceeds to a FULL BUILD:

  * `build-cli.sh --no-bundl` (one letter short) builds the bundle anyway and
    says nothing. So does `--nobundle`, `--no_bundle`, and `--no-bundle=true`.
  * `build-cli.sh --help` does not print help. It runs the entire build.

That last one is not hypothetical politeness: this script's own header advertises `Usage: build-cli.sh [--bundle] [--verify]`, so the two flags a reader is told about are precisely the two that do nothing (both default to true), while the two that do something -- `--no-bundle`, `--no-verify` -- are undocumented. This port reproduces the silence exactly, because a port that started
rejecting arguments would fail differently from the script it claims to be equivalent to. `parse_flags` is exported so the acceptance rule is readable in one place. Reported to the driver; the repair is a cutover-box decision.

-----------------------------------------------------------------------------
DEFECT 2, REPRODUCED AND NOT FIXED: THE BUILD'S EXIT CODE IS DISCARDED
-----------------------------------------------------------------------------
`if npm run build:cli; then ... else log_error "CLI build failed"; exit 1; fi` replaces whatever npm exited with by a flat 1. npm distinguishes its own failure modes by status (1 for a failed script, 127 for a missing one, 130 on SIGINT), and every one of them arrives at the caller as 1 with the same sentence. The `if` also means `set -e` never sees the failure, which is why the
script gets to choose a code at all. Reproduced; the twin's three `exit 1`s are the twin's.

-----------------------------------------------------------------------------
`ARG_BUNDLE` / `ARG_VERIFY` ARE READ FROM THE ENVIRONMENT, NOT FROM `parse_args`
-----------------------------------------------------------------------------
`BUNDLE="${ARG_BUNDLE:-true}"` looks like it is reading what `common.sh`'s
`parse_args` (`common.sh:324-353`) writes, and it is NOT: this script never calls `parse_args`. The names are the same by convention only, so the two
variables are plain inherited environment, and exporting `ARG_BUNDLE=false`
turns the bundle off in a way no `--flag` documents. Reproduced, and named here because the resemblance is the trap.

The comparison is `== "true"`, so any other value -- `1`, `yes`, `TRUE` -- reads
as FALSE. `:-` substitutes on unset OR empty, so `ARG_BUNDLE=` takes the `true`
default while `ARG_BUNDLE=1` does not.

-----------------------------------------------------------------------------
ONE DELIBERATE, DOCUMENTED DIVERGENCE: A MISSING `npm` OR `ls`
-----------------------------------------------------------------------------
bash prints `<script path>: line <n>: npm: command not found` and gives the `if` a status of 127, which lands in the `else` arm and exits 1. This port prints the same shape naming its own path and line, and takes the same branch, so the exit code and the script's own message agree; only the interpreter's diagnostic differs. The differential masks the `<path>: line <n>: ` prefix.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE
-----------------------------------------------------------------------------
`os.environ.get("ARG_BUNDLE", "")` and `os.environ.get("ARG_VERIFY", "")`, each
where it is used. No `env = dict(os.environ)` alias: the env-manifest reader
parses direct `os.environ` reads and an alias makes both names invisible to it.

`CLI_VERSION` is NOT read here, and the absence is deliberate: the workflow sets it on this step, but it is consumed by esbuild inside `npm run build:bundle` through ordinary inheritance. The twin does not name it either, and naming it here would create a second place the version-injection contract is written down.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from rediacc_ci import log

# The four flags the twin's `case` recognises, mapped to (variable, value). Held as data so DEFECT 1's acceptance rule is one table rather than four arms, and so a reader can see at a glance that there is no default arm.
FLAGS = {
    "--no-bundle": ("bundle", False),
    "--no-verify": ("verify", False),
    "--bundle": ("bundle", True),
    "--verify": ("verify", True),
}

# `[[ "$BUNDLE" == "true" ]]`: the exact string, not a truthiness test.
TRUE = "true"

# What `--verify` checks for, in the twin's order. The directory FIRST, so a missing `dist/` is reported as a missing directory rather than as a missing file inside one.
DIST_DIR = "packages/cli/dist"
DIST_ENTRY = "packages/cli/dist/index.js"


def console_root() -> pathlib.Path:
    """The repository root, from this file's own location.

    Same derivation and same reasoning as the other two ports in this package: the twin uses `get_repo_root` (`common.sh:205-210`), which has no environment override, so `rediacc_ci.paths.repo_root()` -- which honours `$REDIACC_CI_ROOT` -- is not used.
    """
    # This file: <root>/.ci/rediacc_ci/build/build_cli.py
    return pathlib.Path(__file__).resolve().parents[3]


def parse_flags(argv: list[str], *, bundle: bool, verify: bool) -> tuple[bool, bool]:
    """The twin's `for arg in "$@"; do case ... esac; done`, exactly.

    LAST WINS, because the loop assigns on every match rather than breaking: `--no-bundle --bundle` ends with the bundle ON. UNRECOGNISED ARGUMENTS ARE DROPPED IN SILENCE (DEFECT 1) -- there is no `*)` arm to reproduce, and its absence is the behaviour under test, not an omission here.

    The starting values come from the caller because they are the environment's, not this function's: see the `ARG_BUNDLE`/`ARG_VERIFY` section above.
    """
    state = {"bundle": bundle, "verify": verify}
    for arg in argv:
        if arg in FLAGS:
            name, value = FLAGS[arg]
            state[name] = value
    return state["bundle"], state["verify"]


def _run(argv: list[str], line: int) -> int:
    """One inherited-stream subprocess, returning the status the twin's `if` would have seen.

    Flushes first: this process has already written to stderr through `log`, and a buffered parent interleaving with an unbuffered child is a difference the port would be introducing all by itself.

    A missing binary becomes 127 with bash's own message shape (the documented divergence above), and a non-executable one becomes 126, so the `if` branches the same way it does under bash.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(argv, check=False).returncode
    except PermissionError:
        print(
            "%s: line %d: %s: Permission denied" % (__file__, line, argv[0]),
            file=sys.stderr,
            flush=True,
        )
        return 126
    except OSError:
        print(
            "%s: line %d: %s: command not found" % (__file__, line, argv[0]),
            file=sys.stderr,
            flush=True,
        )
        return 127


def main(argv: list[str]) -> int:
    # STEP 1: the environment supplies the defaults, the flags override them.
    bundle, verify = parse_flags(
        argv,
        bundle=(os.environ.get("ARG_BUNDLE", "") or TRUE) == TRUE,
        verify=(os.environ.get("ARG_VERIFY", "") or TRUE) == TRUE,
    )

    # STEP 2: every path below is repo-relative, so the process moves to the root.
    root = console_root()
    try:
        os.chdir(root)
    except OSError as exc:
        print(
            "%s: line %d: cd: %s: %s" % (__file__, sys._getframe().f_lineno, root, exc.strerror),
            file=sys.stderr,
            flush=True,
        )
        return 1

    log.step("Building CLI...")

    # STEP 3: the workspace build. DEFECT 2: npm's status is discarded and replaced by 1.
    if _run(["npm", "run", "build:cli"], sys._getframe().f_lineno) == 0:
        log.info("CLI build completed")
    else:
        log.error("CLI build failed")
        return 1

    # STEP 4: the single-file bundle, on by default.
    if bundle:
        log.step("Creating CLI bundle...")
        if (
            _run(["npm", "run", "build:bundle", "-w", "@rediacc/cli"], sys._getframe().f_lineno)
            == 0
        ):
            log.info("CLI bundle created")
        else:
            log.error("CLI bundle failed")
            return 1

    # STEP 5: verify, on by default. Two existence tests and a listing.
    #
    # WHAT THIS DOES NOT CHECK, said out loud because the step is named "verify" and a reader will assume more of it than it does: it checks that a directory and one file EXIST. An empty `index.js` left behind by a build that half-ran passes, and so does a stale one from a previous build that this run failed to replace -- nothing here looks at mtime, size or content.
    if verify:
        log.step("Verifying CLI build output...")
        if not pathlib.Path(DIST_DIR).is_dir():
            log.error("CLI dist directory not created")
            return 1
        if not pathlib.Path(DIST_ENTRY).is_file():
            log.error("CLI index.js not found in dist")
            return 1
        log.info("CLI build output verified")
        # The trailing slash is the twin's and is kept: `ls` prints a different header line for a directory operand depending on how it was named when more than one operand is present, and matching argv exactly is cheaper than reasoning about when it matters.
        #
        # Its status is NOT discarded. `ls` here is a plain command under `set -e`, so a non-zero status aborts the twin with `ls`'s own code and the final "CLI build complete" line never prints. That is close to unreachable -- the directory was proven to exist two lines above -- but `ls` also exits 1 on a permission error reading it, and a port that swallowed the status would
        # report a successful build where the twin reported a failed one.
        code = _run(["ls", "-lah", "%s/" % DIST_DIR], sys._getframe().f_lineno)
        if code != 0:
            return code

    log.info("CLI build complete: %s/" % DIST_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
