#!/usr/bin/env python3
"""Port of `.ci/scripts/setup/install-cli-global.sh`.

`npm pack` in `packages/cli`, then `npm install -g` the tarball it produced,
then delete the tarball and report which name the CLI answers to. Sixty-two
lines, used by CI to test the CLI the way a user gets it rather than through
`npm link`.

    .ci/scripts/setup/install-cli-global.sh
    .ci/scripts/setup/install-cli-global.sh --package-dir packages/cli

`--package-dir` is the only option, parsed by `common.sh`'s generic `parse_args`
(so `--package-dir=X` and `--package-dir X` are both accepted), defaulting to
`packages/cli`.

=============================================================================
THE ERROR BRANCH IN THIS SCRIPT IS DEAD CODE, AND THAT IS THE HEADLINE
=============================================================================
`install-cli-global.sh:41-46` reads:

    TARBALL=$(ls -1 rediacc-cli-*.tgz 2>/dev/null | head -n 1)

    if [[ -z "$TARBALL" ]]; then
        log_error "No tarball found after npm pack"
        exit 1
    fi

The `if` can never be true. The file opens with `set -euo pipefail`, and:

  * With no matching file, bash leaves the pattern unexpanded and hands
    `rediacc-cli-*.tgz` to `ls` as a literal operand.
  * GNU `ls` cannot stat it, writes to stderr (discarded by `2>/dev/null`) and
    exits **2**.
  * `head -n 1` reads nothing and exits 0, but `pipefail` makes the PIPELINE's
    status the rightmost non-zero one, so the pipeline is 2.
  * The status of `VAR=$(pipeline)` is the status of the command substitution,
    and `set -e` therefore kills the script THERE -- before the `if` is reached.

Driven on this machine, 2026-09-14, in an empty scratch directory:

    $ cat t.sh
    set -euo pipefail
    TARBALL=$(ls -1 rediacc-cli-*.tgz 2>/dev/null | head -n 1)
    echo "REACHED: [$TARBALL]"
    $ bash t.sh; echo "exit=$?"
    exit=2

`REACHED` never printed. So the real behaviour when `npm pack` produces nothing
is: **exit 2, with not one byte on either stream** -- no `log_error`, no
`No tarball found after npm pack`, nothing. A caller sees a bare 2 and the
message that was written for exactly this case is unreachable. That is the
"exit 1 with zero bytes on both streams" shape, and it looks precisely like a
gate failing for a real reason.

REPRODUCED, NOT REPAIRED. This port returns 2 and prints nothing, and keeps the
unreachable message as a named constant so the string still exists to be grepped
for. Fixing the twin is a cutover-box decision.

=============================================================================
THREE MORE FACTS ABOUT THE TWIN, ALL REPRODUCED
=============================================================================
  1. THE TARBALL IT INSTALLS IS NOT NECESSARILY THE ONE IT JUST PACKED.
     `npm pack` prints the filename it created on stdout, and the script ignores
     it: it re-derives the name by listing the directory and taking
     `head -n 1`, which is the LEXICOGRAPHICALLY FIRST name, not the newest and
     not npm's. `npm pack` does not clean up previous tarballs, and `rm -f`
     at the end removes only the one that was chosen -- so a leftover from an
     earlier run can win every subsequent run. With `rediacc-cli-0.0.0-dev.tgz`
     (the placeholder every package.json in this repo carries) sitting beside
     `rediacc-cli-0.8.3.tgz`, C-collation puts `0.0.0-dev` first and that is
     what gets installed globally. Sorting is byte-wise, so `0.10.0` also sorts
     before `0.9.0`.

  2. `npm pack` AND `npm install -g` ARE UNGUARDED. Neither is wrapped in an
     `if` and neither has a `||`. `set -e` therefore ends the script with npm's
     own exit code and NO `log_error` line -- npm's diagnostics are the only
     explanation the caller gets. Contrast the two `require_dir`-style refusals,
     which do print. Reproduced: this port returns npm's code and adds nothing.

  3. THE FINAL CHECK CANNOT FAIL THE SCRIPT. `command -v rdc`, else
     `command -v rediacc`, else a `log_warn` that says the shell may need
     restarting -- and then exit 0. So "installed globally, and nothing by
     either name is on PATH" is a WARNING. In CI, where no shell is going to be
     restarted, that is a successful install of nothing. The vacuity is in the
     verification step, same as its sibling `build-packages.sh`.

=============================================================================
TWO DIVERGENCES, STATED RATHER THAN DISCOVERED LATER
=============================================================================
`command -v` VERSUS `shutil.which`. `command -v rdc` also answers for shell
functions, aliases and builtins; `shutil.which` sees only files on PATH.
`core.common.require_cmd` records the same gap at its own call site. Nothing
installs `rdc` as a shell function, so the difference is not reachable from this
script -- but it is a difference, and it is here rather than nowhere.

A `parse_args` KEY THAT IS NOT A VALID IDENTIFIER (`--foo.bar`) makes bash's
`printf -v` fail with a message that names `common.sh` and a line number, then
`set -e` ends the run with 2. `core.common.parse_args` raises `RefusalError`
with the message text but no file-and-line prefix, so the exit code matches and
the stderr bytes do not. That quirk belongs to `core.common` (its QUIRK 3) and
is not re-litigated here; no caller of this script passes such a flag.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `PACKAGE_DIR="${ARG_PACKAGE_DIR:-packages/cli}"` (install-cli-global.sh:24).
# `:-` means an EMPTY value falls back too, so `--package-dir=` behaves as if the
# flag were absent rather than refusing.
ARG_KEY = "ARG_PACKAGE_DIR"
DEFAULT_PACKAGE_DIR = "packages/cli"

# The tarball pattern, from install-cli-global.sh:41. `npm pack` names its output
# `<name>-<version>.tgz` with the scope stripped, so `@rediacc/cli` packs as
# `rediacc-cli-<version>.tgz`.
TARBALL_GLOB = "rediacc-cli-*.tgz"

# GNU coreutils `ls` exits 2 for "serious trouble", which includes an operand it
# cannot stat. Under `pipefail` that becomes the pipeline's status and under
# `set -e` it becomes the SCRIPT's status. Named rather than inlined so the
# provenance of a bare `2` is readable at the return statement.
LS_CANNOT_STAT_EXIT = 2

# The message install-cli-global.sh:44 would print if it could be reached. Kept
# as a constant, unused by any code path, so that the string a reader greps for
# still exists in the port -- and so its absence from every run's output is a
# deliberate, documented match rather than an omission.
UNREACHABLE_NO_TARBALL = "No tarball found after npm pack"

# The two names the twin probes for, in order (install-cli-global.sh:58-64).
CLI_NAMES = ("rdc", "rediacc")


def package_dir(argv: list[str]) -> str:
    """`parse_args "$@"` then `${ARG_PACKAGE_DIR:-packages/cli}`.

    `common.parse_args` is the ported `common.sh:324-353`, so all of its rules
    apply unchanged: `--package-dir=X` splits on the first `=`; `--package-dir X`
    consumes the next token unless it starts with `--`; a bare `--package-dir` at
    the end of the argv stores the STRING `true`, which then fails `require_dir`
    with `Required directory 'true' does not exist`. That last one reads like a
    bug in the port the first time it is seen and is the twin exactly.
    """
    parsed = common.parse_args(argv)
    return parsed.get(ARG_KEY) or DEFAULT_PACKAGE_DIR


def choose_tarball() -> str | None:
    """`ls -1 rediacc-cli-*.tgz 2>/dev/null | head -n 1`, in the current directory.

    Returns the lexicographically first match, or None when there is none -- and
    None is the case the twin cannot survive (see the module docstring), so the
    caller turns it into a silent exit 2 rather than into the message the twin
    has written for it.

    SORTED BYTE-WISE, matching `ls` under `LC_ALL=C`. Python's `sorted` on `str`
    compares code points, which agrees with C collation for the ASCII filenames
    npm produces. Under a collating locale `ls` would order differently and this
    would not; every caller of this script runs under CI's `LC_ALL=C`, and the
    differential pins it.

    A DANGLING SYMLINK STILL COUNTS, in both: `glob` matches on the name and `ls`
    lists the entry, neither stats the target.
    """
    matches = sorted(glob.glob(TARBALL_GLOB))
    return matches[0] if matches else None


def remove_tarball(name: str) -> None:
    """`rm -f "$TARBALL"` (install-cli-global.sh:55).

    `missing_ok` is what `-f` means. Any OTHER `OSError` -- a read-only directory,
    a permission problem -- would make `rm` exit non-zero and `set -e` end the
    twin, so it must not become a Python traceback here; the caller turns it into
    a non-zero return. That is the one place the two cannot print the same bytes,
    because the twin's bytes are `rm`'s own message and this port never runs `rm`.
    """
    try:
        os.unlink(name)
    except FileNotFoundError:
        return


def npm(args: list[str], **kwargs) -> int:
    """One `npm` child with BOTH streams inherited, as the twin leaves them.

    `npm pack` writes the filename it created to stdout and its progress to
    stderr; the twin captures neither, and a port that captured either would
    change what a CI log contains and would hold a minutes-long global install
    silent until it finished.
    """
    return subprocess.run(["npm", *args], check=False, **kwargs).returncode


def main(argv: list[str]) -> int:
    try:
        target = package_dir(argv)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    # `cd "$(get_repo_root)"` BEFORE the validation, so `--package-dir` is always
    # interpreted relative to the repo root and never to the caller's cwd
    # (install-cli-global.sh:27).
    os.chdir(common.repo_root())

    try:
        common.require_dir(target)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    log.step("Installing CLI globally from %s..." % target)

    os.chdir(target)

    log.step("Creating npm package tarball...")
    code = npm(["pack"])
    if code != 0:
        # UNGUARDED IN THE TWIN: `set -e` ends it here with npm's code and no
        # message of its own. Fact 2.
        return code

    tarball = choose_tarball()
    if tarball is None:
        # THE DEAD BRANCH. The twin dies at the assignment with exit 2 and zero
        # bytes; `UNREACHABLE_NO_TARBALL` is the line it never gets to print.
        return LS_CANNOT_STAT_EXIT

    log.step("Installing %s globally..." % tarball)
    code = npm(["install", "-g", tarball])
    if code != 0:
        return code

    try:
        remove_tarball(tarball)
    except OSError as exc:
        # `rm -f` failed for a reason `-f` does not cover. The twin's `set -e`
        # ends with 1 and rm's message; this ends with 1 and Python's. Named in
        # the docstring as the one byte-level divergence in the file.
        log.error(str(exc))
        return 1

    log.info("CLI installed globally")

    for name in CLI_NAMES:
        if shutil.which(name) is not None:
            log.info("CLI available as '%s'" % name)
            break
    else:
        # Fact 3: a warning, then exit 0.
        log.warn("CLI command not found in PATH (may need to restart shell)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
