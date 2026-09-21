#!/usr/bin/env python3
"""Port of `.ci/scripts/security/shfmt.sh`.

W7P6 wave 28. The bash twin stays the LIVE registered gate (`check:ci-shell-format`, step "Shell format"); this module is its VERIFIED-EQUIVALENT ALTERNATIVE, proved on both streams by
`.ci/rediacc_ci/tests/test_security_shfmt.py` and by the K=5 shadow ledger
`.ci/shadow/w7p6-shfmt.observations.jsonl`. Nothing is repointed at this file. Cutover is a separate, later, driver-only step.

WHAT IT DOES. Acquires shfmt AT THE PIN through `rediacc_ci.core.toolchain` (the already-landed port of `.ci/scripts/lib/toolchain.sh`), refuses to report a
verdict if fewer than `${SHFMT_MIN_FILES:-200}` shell scripts are visible, then
runs `shfmt -i 4 -ci -d` over four deliberately-asymmetric scopes: all of `.ci`, all of `.claude`, `./run.sh` alone, and `scripts/dev` plus `scripts/ops`.

REAL RUNS OR STUBS: BOTH.

  * The HAPPY AND FINDING PATHS run the REAL shfmt against this repository's
    REAL 570-odd shell scripts. `-d` is DIFF mode: shfmt reads each file and
    writes a unified diff to stdout. It is `-w` that writes, and `-w` is not
    used anywhere in the twin. The differential hashes every file in all four
    scopes before and after each real-run case and refuses a byte of drift, so
    "read-only" is asserted rather than assumed.
  * The ACQUISITION-FAILURE path (exit 77, the CANNOT_RUN verdict) runs against
    a scratch `PATH` with no shfmt, an empty scratch tool cache, no `go`, and a
    RECORDING FAKE `curl` that fails SILENTLY. Silently on purpose: a real curl
    would print `curl: (22) ...` of its own, and the two sides route curl's
    stderr differently (see the DEFECT note below), so a talking fake would make
    the differential fail for a reason that is not this port's.
  * The VACUITY-FLOOR path runs in a scratch tree with a real shfmt and three
    files, driven by `$SHFMT_MIN_FILES`.

THE ONE NAMED DIVERGENCE, AND IT IS THE INTERESTING ONE: FILE ORDER.

The twin enumerates with `find <root> -name '*.sh' -type f -exec shfmt ... {} +`
and POSIX leaves find's traversal order UNSPECIFIED. That is not theoretical here. Measured 2026-09-14 on this host:

    $ find --version | head -1
    bfs 4.1.1

`bfs` is a breadth-first drop-in for find. GNU findutils, which is what `ubuntu-latest` runs in CI, is depth-first pre-order in readdir order. Over `.ci` alone the two produce the SAME 300-odd files in a VISIBLY different sequence (`.ci/tutorials/lib/*.sh` lands at position 11 under one and position 120 under the other). So the twin's output ORDER is a property of whichever `find`
is installed, not a property of the gate.

This port therefore enumerates in BYTE ORDER, which is deterministic everywhere, and the differential:

  * compares exit code and stderr BYTE FOR BYTE;
  * compares the non-diff stdout lines BYTE FOR BYTE, in order;
  * compares the per-file diff BLOCKS as a MULTISET;
  * and separately asserts that the twin's block order is exactly the ambient
    `find`'s traversal order, so the residual difference is ATTRIBUTED rather
    than waved through.

Nothing else is normalised.

A DEFECT IN THE TWIN, REPRODUCED NOT REPAIRED. Under `set -e`, a scope whose `find ... -exec shfmt` reports differences ABORTS THE WHOLE SCRIPT, so the three scopes after the first failing one are NEVER CHECKED and the operator is never told. Measured on this tree 2026-09-14: `.ci` alone reports 36 diffs, the run exits 1 after `info: Checking .ci/**/*.sh`, and `.claude`,
`./run.sh`, `scripts/dev` and `scripts/ops` produce no output at all. A reader who fixes the 36 `.ci` findings discovers the next scope's findings only on the next run.
Reproduced exactly (this port stops at the same place with the same bytes);
fixing it is a cutover-box decision, not a port's.

A SECOND, SMALLER ONE: `log_error()`/`log_info()`/`log_success()` here interpolate `"$1"`, not `"$*"`, so `log_error a b` silently drops `b` -- the same shape as the 2026-09-06 emit-advisory defect. Every call site in this twin passes exactly one argument, so it is latent rather than live. Reproduced by giving this port's helpers one parameter each.

WHY NOT `rediacc_ci.log`. This twin does NOT source `common.sh`. It defines its own `error: `/`info: `/`success: ` logger with a DIFFERENT colour rule (colour
unless `CI=true`, with no tty test at all, so a developer piping this gate into
a file gets escape sequences) and a different stream split (`info` and `success` on STDOUT, `error` on stderr). The house logger is a port of common.sh's logger and would be wrong on all three counts, so the twin's shape is reproduced here and named rather than silently upgraded.

`require_cmd` / `require_var` ARE NOT CALLED HERE, so the multi-argument
`require_cmd` defect (`common.sh:141-148` binds `local cmd="$1"` and ignores the
rest) does not apply. Checked, and recorded so the next reader does not repeat the check.

ONE MORE NAMED DIVERGENCE THIS PORT ADDS: `paths.repo_root()` honours `$REDIACC_CI_ROOT` and the twin's `SCRIPT_DIR/../../..` does not.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.core import toolchain

# `-i 4` four-space indent, `-ci` indent switch cases, `-d` diff mode (show what would change, exit non-zero if changes are needed). The twin keeps these in one space-separated `SHFMT_OPTS` string and word-splits it at four call sites, each carrying a `BLOCKER:` comment saying the splitting is intentional.
SHFMT_OPTS = ("-i", "4", "-ci", "-d")

# The vacuity floor's default. Measured 2026-09-04: 568 .sh files across the four scopes; re-measured 2026-09-21 at 334 after the bash-retirement campaign, so the margin is 134 files and shrinking. The floor stays well under the count, to catch a broken enumeration rather than today's file count, and is restated on each retirement batch so a closing margin is visible early.
DEFAULT_MIN_FILES = "200"

# The three roots the floor counts, in the twin's argv order (order is irrelevant to a count and is kept so the two reads match on inspection).
FLOOR_ROOTS = (".ci", ".claude", "scripts")

# The two optional scopes at the end of main, in the twin's `for dir in` order. `scripts/docker` became `scripts/ops` on 2026-09-20 with W9 P2's move; the `is_dir()` guard below skips a scope that has stopped existing, so a stale name here would leave the whole scope unformatted and still report success.
OPTIONAL_SCOPES = ("scripts/dev", "scripts/ops")

# ANSI, matching the twin's own literals. Not `rediacc_ci.log`'s; see the module docstring.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"


def colours() -> tuple[str, str, str]:
    """`if [[ "${CI:-}" == "true" ]]` (:22-26). NO tty test, deliberately.

    Read straight from `os.environ` at the call site rather than through a captured `env` dict: an alias is how a gate ends up reading a snapshot taken before the value it cares about was set.
    """
    if os.environ.get("CI", "") == "true":
        return "", "", ""
    return RED, GREEN, NC


def log_error(message: str) -> None:
    """`echo -e "${RED}error: $1${NC}" >&2`. ONE parameter; see the docstring."""
    red, _green, nc = colours()
    print("%serror: %s%s" % (red, message, nc), file=sys.stderr)


def log_success(message: str) -> None:
    """`echo -e "${GREEN}success: $1${NC}"`. STDOUT, not stderr."""
    _red, green, nc = colours()
    print("%ssuccess: %s%s" % (green, message, nc))


def log_info(message: str) -> None:
    """`echo "info: $1"`. STDOUT, no `-e`, no colour even off CI."""
    print("info: %s" % message)


# --------------------------------------------------------------------------- Enumeration ---------------------------------------------------------------------------


def shell_files(root: pathlib.Path) -> list[str]:
    """Every `*.sh` regular file under `root`, in BYTE order. See the docstring.

    `-type f` and NOT following symlinks, both directions: a symlink to a script is not a regular file to `find -P`, and a symlinked directory is not
    descended into. `os.scandir` with `follow_symlinks=False` answers both the
    same way.

    FIXED 2026-09-15: was a hand-rolled `os.scandir` stack that did not exclude `.claude/worktrees/` (sibling CHECKOUTS of this repository for isolated sub-agent sessions, git-excluded via `.git/info/exclude:11` so invisible to git and to CI, but not to a raw directory walk). A peer's worktree turned `test_security_shfmt` and
    `test_gate_vacuity_floors::test_shfmt_accepts_the_real_corpus` red on 2026-09-13 over files that are not in the repository at all. Landed on both sides at once, as it had to be: `-not -path './.claude/worktrees/*'` on `.ci/scripts/security/shfmt.sh:72` and `:104` (the bash twin `check:ci-shell-format` actually runs), and `paths.walk_tree` here -- a one-sided fix would have made
    this port's real-tree differential in `test_security_shfmt.py` report the (now intended) difference from the twin as a MISMATCH.
    """
    found: list[str] = []
    for dirpath, _dirnames, filenames in paths.walk_tree(root):
        for name in filenames:
            if not name.endswith(".sh"):
                continue
            path = pathlib.Path(dirpath) / name
            # `find -P -type f`: a symlinked file is NOT type f, and os.walk's `filenames` does not make that distinction on its own -- it lists a symlink-to-file exactly like a real file.
            if not path.is_symlink() and path.is_file():
                found.append(str(path))
    return sorted(found)


def floor_count() -> int:
    """`find .ci .claude scripts -name '*.sh' -type f 2>/dev/null | wc -l`.

    RELATIVE to the current directory, because `main` has already reproduced the twin's `cd "$ROOT_DIR"`. That `cd` is load-bearing and not a tidiness: every scope below is named RELATIVELY, so the paths shfmt prints in its diff headers are `.ci/lib/account.sh`, not absolute. Handing shfmt an absolute path changes the bytes of every diff header it emits.

    A ROOT THAT DOES NOT EXIST IS SKIPPED, not fatal: `find` writes "No such file or directory" to the stderr the twin sends to /dev/null and still walks the roots it can reach.
    """
    total = 0
    for name in FLOOR_ROOTS:
        root = pathlib.Path(name)
        if not root.is_dir():
            continue
        total += len(shell_files(root))
    return total


# --------------------------------------------------------------------------- Running the tool ---------------------------------------------------------------------------


def run_shfmt(binary: str, targets: list[str]) -> int:
    """`shfmt -i 4 -ci -d <targets>`, streams INHERITED. Returns its exit code.

    Inherited rather than captured so a large diff reaches the caller's stdout exactly as the twin's does, and so shfmt's own parse errors stay on stderr instead of being reordered into stdout by a buffer of ours.
    """
    if not targets:
        # `find` with no match runs the `-exec ... +` command ZERO times and exits 0. Passing an empty list to shfmt would make it read STDIN.
        return 0
    sys.stdout.flush()
    sys.stderr.flush()
    proc = subprocess.run([binary, *SHFMT_OPTS, *targets], check=False)
    return proc.returncode


def check_scope(binary: str, relative: str) -> int:
    """One `find <relative> ... -exec shfmt ... {} +` scope, RELATIVE to cwd.

    RETURNS 1, NOT shfmt's OWN CODE, on a failing scope. Under `set -e` the twin exits with FIND's status, and find reports "an -exec command failed" as exactly 1 regardless of what the child returned. The direct `./run.sh` call has no find in front of it and therefore does return shfmt's own code; that asymmetry is the twin's and is reproduced in `main`.
    """
    return 1 if run_shfmt(binary, shell_files(pathlib.Path(relative))) != 0 else 0


# --------------------------------------------------------------------------- main ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    """`main` (:39-115). argv is accepted and ignored, as `main "$@"` does."""
    del argv
    # `cd "$ROOT_DIR"` (:40). Every scope below is named relatively and the relative spelling reaches shfmt's diff headers, so this is observable.
    os.chdir(paths.repo_root())

    log_info("Checking shell script formatting")

    # ACQUIRE AT THE PIN, not merely "present". `toolchain_acquire`'s own messages go to stderr as it produces them, before the block below.
    binary, messages = toolchain.acquire("shfmt")
    for line in messages:
        print(line, file=sys.stderr)
    if binary is None:
        log_error("shfmt is unusable for this gate -- CANNOT RUN, not a verdict")
        log_info("Every lane's toolchain: .ci/scripts/lib/toolchain.sh --report")
        log_info(
            "Or run the gate where it is pinned: "
            "./run.sh devbox exec -- .ci/scripts/security/shfmt.sh"
        )
        # 77 = CANNOT_RUN, the convention check-python-lint.sh:170 established.
        # The ci-runner classifies it as BLOCKED: counted, named, recorded in the push receipt and warned about, but never a claim about the code.
        return 77

    sys.stdout.flush()
    subprocess.run([binary, "--version"], check=False)

    # VACUITY FLOOR. Every scope below is an enumeration, and an enumeration that matches nothing lints nothing and exits 0.
    minimum = os.environ.get("SHFMT_MIN_FILES", "") or DEFAULT_MIN_FILES
    seen = floor_count()
    if seen < int(minimum):
        log_error("VACUOUS: found %d shell script(s), floor %s." % (seen, minimum))
        log_error("The enumeration lost its corpus; refusing to report formatting clean.")
        return 1

    log_info("Checking .ci/**/*.sh")
    rc = check_scope(binary, ".ci")
    if rc != 0:
        return rc

    # Claude hooks carry live PR policy, so policy-critical shell gets formatted too. DELIBERATELY NARROWER THAN shellcheck.sh: that gate reports CORRECTNESS defects and is worth surfacing everywhere, this one reports FORMATTING, and widening it would demand reformatting 11 files nobody is otherwise touching. Widen only alongside a decision to reformat them.
    log_info("Checking .claude/**/*.sh")
    rc = check_scope(binary, ".claude")
    if rc != 0:
        return rc

    log_info("Checking ./run.sh")
    # NO find HERE, so this one returns shfmt's OWN exit code. See `check_scope`. `./run.sh` VERBATIM, leading dot-slash included: shfmt echoes the argument it was given into `diff ./run.sh.orig ./run.sh`.
    rc = run_shfmt(binary, ["./run.sh"])
    if rc != 0:
        return rc

    # The top-level scripts/*.sh files are intentionally excluded: they predate the formatter. New helper scripts go in scripts/dev/ or scripts/ops/.
    for relative in OPTIONAL_SCOPES:
        if not pathlib.Path(relative).is_dir():
            continue
        log_info("Checking %s/**/*.sh" % relative)
        rc = check_scope(binary, relative)
        if rc != 0:
            return rc

    log_success("Shell script formatting passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
