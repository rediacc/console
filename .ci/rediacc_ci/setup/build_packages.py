#!/usr/bin/env python3
"""Port of `.ci/scripts/setup/build-packages.sh`.

Thirty-five lines: wipe the TypeScript build cache, run `npm run build:packages`, then look at whether `packages/shared/dist` came back. The whole file is four steps and one of them does not do what its name suggests, which is the reason this docstring is longer than the script.

-----------------------------------------------------------------------------
WHY THE CACHE IS WIPED FIRST, IN THE TWIN'S OWN WORDS
-----------------------------------------------------------------------------
`build-packages.sh:15-17`: "Clean stale TypeScript build cache to prevent module resolution issues. This is necessary because tsbuildinfo files can cause incremental builds to skip emitting files when paths change or when switching between branches."

That is the entire justification for a `rm -rf` in a setup script, and it is load-bearing: `tsc --build` decides what to emit by comparing timestamps recorded in `*.tsbuildinfo`, so after a branch switch that moves a path it can conclude everything is up to date and emit nothing. The build then "succeeds" and `dist/` holds the previous branch's output. Deleting `dist` AND the
tsbuildinfo files together is what makes the following build unconditional.

-----------------------------------------------------------------------------
THE VERIFICATION IS A WARNING, NOT A CHECK. REPRODUCED, AND REPORTED
-----------------------------------------------------------------------------
`build-packages.sh:29-35` loops over a one-element list of expected outputs and, when the directory is absent, prints

    ⚠ Package directory packages/shared/dist not found (may be expected)

and carries on to exit 0. Put that next to the `rm -rf` eleven lines above it and the shape is complete: the script DELETES `packages/shared/dist`, runs a build, finds the directory gone, calls that "may be expected", and reports success. A build that silently emitted nothing -- which is exactly the failure the tsbuildinfo wipe exists to prevent -- exits 0 here with a warning
nobody greps for. The one anti-vacuity opportunity in the file is spent on a `log_warn`.

Reproduced byte for byte, including the parenthetical. Fixing a twin is a cutover-box decision and a port that quietly hardened this would stop being evidence about the original.

TWO SMALLER FACTS, ALSO REPRODUCED:

  1. `PACKAGES=("packages/shared/dist")` is an array with ONE element and a loop
     around it. The loop is a promise of more entries that never arrived, so
     "verified" means one directory exists, and the count is not printed.

  2. `log_debug` (common.sh:51-55) prints only when `DEBUG` is exactly the string
     `true`. So on every normal run the line `Cleaning TypeScript build cache...`
     is INVISIBLE, and the `rm -rf` above happens with no output at all. A
     developer watching this script sees `Building shared packages...` and then
     npm; the deletion is silent. `DEBUG=1` is not enough -- `DEBUG=true` is the
     literal the twin tests, and `rediacc_ci.log` matches it.

-----------------------------------------------------------------------------
THE GLOB, WHICH IS THE ONE PLACE A TRANSCRIPTION COULD GO WRONG
-----------------------------------------------------------------------------
`rm -rf packages/shared/dist packages/shared/*.tsbuildinfo` is expanded by bash before `rm` ever runs, and bash has no `nullglob` here, so:

  * With matches, `rm` receives the expanded, sorted list.
  * With NO matches, `rm` receives the pattern LITERALLY -- `packages/shared/
    *.tsbuildinfo` as one argument -- and `-f` swallows the resulting "No such
    file or directory". Nothing is printed and the exit code stays 0.
  * A leading dot is not matched by `*` in either bash or `glob`, so a file
    literally named `.tsbuildinfo` survives both implementations.

This port globs in Python and removes what it finds, which reproduces all three cases: the empty match removes nothing, exactly as `rm -f` on a nonexistent literal removes nothing.

`rm -rf` ALSO REMOVES A NON-DIRECTORY. If `packages/shared/dist` is a regular file or a symlink, `rm -rf` deletes it without complaint; `shutil.rmtree` would raise `NotADirectoryError`. `remove_path` below branches on that, because "dist is a stale symlink into another worktree" is a real state in a repo that uses git worktrees and a port that crashed on it would be worse than the
twin.

STREAMS ARE INHERITED FOR npm, NEVER CAPTURED. `npm run build:packages` is a `tsc` build that prints its diagnostics as it goes; capturing them would hold every line until the build finished and lose them entirely if it hung.
"""

from __future__ import annotations

import glob
import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# The npm script the twin runs (build-packages.sh:21). One string, so the differential's expected call log and the code cannot drift.
BUILD_SCRIPT = "build:packages"

# The two arguments of the `rm -rf` (build-packages.sh:19), in the twin's order. The second is a PATTERN and is glob-expanded; the first is a literal path.
DIST_DIR = "packages/shared/dist"
TSBUILDINFO_GLOB = "packages/shared/*.tsbuildinfo"

# `PACKAGES=("packages/shared/dist")` (build-packages.sh:30). A tuple of one,
# kept as a sequence because the twin kept it as an array: the loop below is the twin's loop, and collapsing it to a single `if` would hide that the script was written to check more than one thing and never did.
EXPECTED_OUTPUTS = (DIST_DIR,)


def remove_path(path: str) -> None:
    """`rm -rf <path>` for one already-expanded argument.

    Three cases, matching `rm -rf` and not `shutil.rmtree`:

      * A directory (or a symlink TO a directory named with a trailing slash --
        not a case this script produces) is removed recursively.
      * Anything else that exists, including a regular file and a dangling
        symlink, is unlinked. `rm -rf` does not care what it is.
      * A path that does not exist is a silent no-op, which is what `-f` buys.

    `os.path.islink` is tested BEFORE `os.path.isdir`, because `isdir` follows symlinks: a symlink pointing at a directory would otherwise be handed to `rmtree`, which refuses it with `NotADirectoryError` on some platforms and, worse, could be read as an instruction to delete the TARGET. `rm -rf` on a symlink removes the link and never touches what it points at.
    """
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
        return
    if os.path.isdir(path):
        shutil.rmtree(path)


def clean_targets(root: pathlib.Path | None = None) -> list[str]:
    """Every path the twin's `rm -rf` would actually act on, in its order.

    A PURE FUNCTION, separate from the removal, so the differential can assert WHICH paths a run would delete without deleting anything -- and so the glob semantics above are testable rather than described. Relative paths, because the twin's are relative to the repo root it has just `cd`ed into.

    The literal `dist` path is always first and is returned even when it does not exist: `rm -rf` is handed it unconditionally, and a caller counting targets should see the same list bash built, not the subset that happened to be present.
    """
    base = pathlib.Path.cwd() if root is None else pathlib.Path(root)
    matches = sorted(glob.glob(str(base / TSBUILDINFO_GLOB)))
    return [DIST_DIR, *[os.path.relpath(m, base) for m in matches]]


def main(argv: list[str]) -> int:
    # THE TWIN PARSES NOTHING. `build-packages.sh` has no `parse_args` call and no `case` loop; its usage line reads `build-packages.sh` with no options. Every argument is therefore ignored, including `--help`, and that is reproduced rather than improved: an argparse here would exit 2 on `--help` where the twin builds the packages.
    del argv

    os.chdir(common.repo_root())

    log.step("Building shared packages...")

    # Silent unless DEBUG=true. Fact 2 above.
    log.debug("Cleaning TypeScript build cache...")
    for target in clean_targets():
        remove_path(target)

    if subprocess.run(["npm", "run", BUILD_SCRIPT], check=False).returncode == 0:
        log.info("Shared packages built successfully")
    else:
        log.error("Failed to build shared packages")
        return 1

    for pkg in EXPECTED_OUTPUTS:
        if os.path.isdir(pkg):
            log.info("Verified: %s exists" % pkg)
        else:
            # A WARNING, AND THEN EXIT 0. See the second section of the module docstring; this is the line that lets a no-op build pass.
            log.warn("Package directory %s not found (may be expected)" % pkg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
