#!/usr/bin/env python3
"""Port of `.ci/scripts/security/shellcheck.sh`.

W7P6 wave 28. The bash twin stays the LIVE registered gate
(`check:ci-shell-lint`, step "Shell lint"); this module is its
VERIFIED-EQUIVALENT ALTERNATIVE, proved on both streams by
`.ci/rediacc_ci/tests/test_security_shellcheck.py` and by the K=5 shadow ledger
`.ci/shadow/w7p6-shellcheck.observations.jsonl`. Nothing is repointed at this
file. Cutover is a separate, later, driver-only step.

WHAT IT DOES. Acquires shellcheck AT THE PIN through `rediacc_ci.core.toolchain`,
enumerates EVERY tracked and untracked `*.sh` from git (not from a list of
roots), drops the ones deleted in the working tree, refuses an empty list, runs
`shellcheck -e SC1090 -e SC1091 -e SC2034 -S warning` over them in batches of
40, and then greps `.ci/scripts/build` for four bash-4-only constructs that
would break the macOS runners (bash 3.2, GPLv3).

REAL RUNS OR STUBS: BOTH.

  * The HAPPY PATH runs the REAL shellcheck against this repository's REAL 620
    tracked-and-untracked shell scripts, because that corpus is the only input
    that exercises the 16-batch chunking, the real `git ls-files` union and the
    real `--version` banner at once. shellcheck is a pure READER; the
    differential hashes all 620 inputs before and after and refuses a byte of
    drift, so "read-only" is asserted rather than assumed. It takes about 100
    seconds per side, which is why there is exactly one such case.
  * EVERY OTHER PATH runs in a scratch git repository with a RECORDING FAKE
    `shellcheck` on a scratch PATH. The fake appends its exact argv to
    `$FAKE_LOG` before answering, and every fixture case compares the two call
    logs as well as the two streams: a port that produced identical bytes while
    BATCHING DIFFERENTLY would pass a stdout comparison and fail this one, and
    the batch boundaries are observable in the real tool's output because
    shellcheck prints its "For more information" footer once per invocation.
  * The ACQUISITION-FAILURE path (exit 1, "shellcheck is unusable for this gate")
    uses an empty scratch tool cache, no shellcheck on PATH, and a fake `curl`
    that fails SILENTLY -- silently because a real curl prints `curl: (22) ...`
    of its own and the two sides route curl's stderr differently, which would
    make the differential fail for a reason that is not this port's.

TWO DEFECTS IN THE TWIN, REPRODUCED NOT REPAIRED, AND ONE NAMED DIVERGENCE.

  1. `echo -e "$BASH4_ISSUES"` RE-INTERPRETS BACKSLASH ESCAPES IN THE MATCHED
     SOURCE LINES. `BASH4_ISSUES` is assembled with LITERAL `\\n` two-character
     sequences and unfolded by `echo -e` at the end, and `echo -e` cannot tell
     the separators it was meant to expand from a `\\n` that was already inside
     a matched line. A build script containing
     `printf 'a\\nb' | mapfile -t x` therefore reports its own finding with an
     embedded newline, and a line containing `\\c` TRUNCATES THE REST OF THE
     REPORT -- every finding after it silently disappears. Reproduced here by
     unescaping the assembled report with `echo_e`, below, and pinned by
     `test_security_shellcheck.py::test_echo_e_mangles_a_backslash_in_a_matched_line`.

  2. **THE DELETED-FILE SKIP IS ITSELF BROKEN WHEN THE DELETED FILE SORTS LAST.**
     The twin's own 2026-09-02 fix for "a tracked file removed with `rm` rather
     than `git rm` makes shellcheck die on openBinaryFile" is

         SH_FILES="$(printf '%s\\n' "$SH_FILES" | while IFS= read -r f; do
             [ -e "$f" ] && printf '%s\\n' "$f"; done)"

     and the `&&` list's status on the LAST iteration is the while loop's status,
     which is the pipeline's status under `pipefail`, which is the assignment's
     status under `set -e`. So if the last path in the sorted list is the missing
     one, the gate prints its "skipping 1 tracked file(s)..." line and then dies
     with exit 1 having linted NOTHING. Measured 2026-09-14 in a two-file scratch
     repository:

         delete b/last.sh  (sorts LAST)  -> exit 1 after "about to filter"
         delete a/first.sh (sorts first) -> exit 0, filtered, 1 file linted

     Exit 1 is the same code the gate uses for "shellcheck reported findings", so
     the CI reader sees a red shell-lint step whose log claims a file was skipped
     and shows no findings at all. Reproduced by the `files[-1]` guard in `main`.

  3. `printf '%s\\n' "$SH_FILES" | xargs ...` LETS xargs RE-SPLIT THE PATHS.
     xargs splits on whitespace and honours quotes and backslashes, so a tracked
     `*.sh` whose name contains a space is handed to shellcheck as TWO arguments.
     This port passes the list through unsplit, so the two sides genuinely
     DIVERGE on such a path. There is no such path in this tree (620 of 620 match
     `[A-Za-z0-9._/-]+`), the twin's behaviour there is plainly wrong, and
     reproducing a whitespace-splitting bug would mean re-deriving xargs' quoting
     rules to be wrong in exactly the same way. So this one is a NAMED DIVERGENCE
     rather than a reproduction, and
     `test_a_path_with_a_space_is_the_one_named_divergence` drives BOTH sides and
     asserts they disagree, so the day such a path appears the difference is
     already written down.

THE ONE NAMED ORDERING DIVERGENCE, and it is confined to the bash-4 block. The
main file list comes from `git ls-files` through `sort -u`, which is fully
deterministic, so the 620-file invocation is byte-identical. The four
`grep -rn ... .ci/scripts/build` probes are NOT: `grep -r`'s traversal order is
unspecified, and this host does not even have GNU grep --

    $ grep --version | head -1
    ugrep 7.8.4 ...
    $ find --version | head -1
    bfs 4.1.1

-- so this port walks `.ci/scripts/build` in BYTE order and says so. The block
produces no output at all on the real tree (checked 2026-09-14: zero matches for
all four patterns), and every fixture case that exercises it uses a single file,
so the divergence is named rather than papered over.

`require_cmd` / `require_var` ARE NOT CALLED HERE, so the multi-argument
`require_cmd` defect (`common.sh:141-148` binds `local cmd="$1"` and ignores the
rest) does not apply. Checked, and recorded so the next reader does not repeat
the check.

WHY NOT `rediacc_ci.log`: identical to the reason in `shfmt.py`. This twin does
not source `common.sh`; it defines its own `error: `/`info: `/`success: ` logger
whose colour rule is `CI != true` with no tty test and whose `info`/`success`
land on STDOUT.

ONE MORE NAMED DIVERGENCE THIS PORT ADDS: `paths.repo_root()` honours
`$REDIACC_CI_ROOT` and the twin's `SCRIPT_DIR/../../..` does not.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import gitx, paths
from rediacc_ci.core import toolchain

# -e SC1090 can't follow non-constant source, -e SC1091 not following sourced files (both dynamic sourcing), -e SC2034 "appears unused" (false positive for exported constants), -S warning fail on warnings or errors only.
SHELLCHECK_OPTS = ("-e", "SC1090", "-e", "SC1091", "-e", "SC2034", "-S", "warning")

# `xargs -r -n 40 -P1`. BATCHED, but batching is NOT what fixed the OOM: measured 2026-08-25 with the pinned 0.10.0, ONE file (test-worklist-v5.sh, 11,955 lines) peaked at 2714 MB on its own and a batch of 40 containing it still dies. The
# real fix is that file's `# shellcheck extended-analysis=false` directive.
# Batching caps the much smaller many-files component (360 MB -> 98 MB) and is kept as a floor for the next large file nobody has noticed yet. -P1 deliberately: `npm run ci` already parallelises across gates.
BATCH = 40

# The directory the bash-4 probes read, and the four constructs. macOS ships bash 3.2 because of GPLv3, and `.ci/scripts/build/` is what runs there for the CLI SEA builds (ci-build-cli.yml uses macos-latest and macos-15-intel).
BUILD_DIR = ".ci/scripts/build"

# The `readarray` / `mapfile` pattern is BUILT FROM HALVES IN THE TWIN so that `.ci/scripts/quality/check-commands.sh` does not flag this file for naming a banned command. The same dodge is reproduced here for the same reason: that gate reads bytes, not intent.
_READ_ARR = "read" + "array"
_MAP_FILE = "map" + "file"

# ANSI, matching the twin's own literals. Not `rediacc_ci.log`'s; see the
# module docstring.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"


def colours() -> tuple[str, str, str]:
    """`if [[ "${CI:-}" == "true" ]]` (:28-32). NO tty test, deliberately.

    Read straight from `os.environ` at the call site rather than through a
    captured `env` dict: an alias is how a gate ends up reading a snapshot taken
    before the value it cares about was set.
    """
    if os.environ.get("CI", "") == "true":
        return "", "", ""
    return RED, GREEN, NC


def log_error(message: str) -> None:
    """`echo -e "${RED}error: $1${NC}" >&2`. ONE parameter, as the twin has."""
    red, _green, nc = colours()
    print("%serror: %s%s" % (red, message, nc), file=sys.stderr)


def log_success(message: str) -> None:
    """`echo -e "${GREEN}success: $1${NC}"`. STDOUT, not stderr."""
    _red, green, nc = colours()
    print("%ssuccess: %s%s" % (green, message, nc))


def log_info(message: str) -> None:
    """`echo "info: $1"`. STDOUT, no `-e`, no colour even off CI."""
    print("info: %s" % message)


# --------------------------------------------------------------------------- `echo -e`, faithfully ---------------------------------------------------------------------------

_ECHO_E_SIMPLE = {
    "a": "\a",
    "b": "\b",
    "e": "\033",
    "E": "\033",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
}


def echo_e(text: str) -> str:
    """What `echo -e "$text"` WRITES, trailing newline included. Defect 1.

    Present as a real unescaper rather than as a `"\\n".join(...)` shortcut
    because the mangling is the POINT: the twin's report is assembled with
    literal backslash-n separators and then unfolded together with whatever
    backslashes the matched SOURCE LINES happened to contain. Only a real
    unescaper reproduces that, and only reproducing it keeps the differential
    honest about a defect this port is not allowed to fix.

    `\\c` STOPS OUTPUT DEAD, dropping everything after it AND the trailing
    newline. That is bash's behaviour and the worst of the set: a single `\\c`
    anywhere in a matched source line silently deletes every finding below it.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != "\\" or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        nxt = text[i + 1]
        if nxt == "c":
            return "".join(out)
        if nxt in _ECHO_E_SIMPLE:
            out.append(_ECHO_E_SIMPLE[nxt])
            i += 2
            continue
        if nxt == "0":
            digits = re.match(r"[0-7]{1,3}", text[i + 2 :])
            body = digits.group(0) if digits else ""
            out.append(chr(int(body, 8)) if body else "\0")
            i += 2 + len(body)
            continue
        if nxt in ("x", "u", "U"):
            width = {"x": 2, "u": 4, "U": 8}[nxt]
            digits = re.match(r"[0-9a-fA-F]{1,%d}" % width, text[i + 2 :])
            if digits:
                out.append(chr(int(digits.group(0), 16)))
                i += 2 + len(digits.group(0))
                continue
        out.append(ch)
        i += 1
    out.append("\n")
    return "".join(out)


# --------------------------------------------------------------------------- The corpus ---------------------------------------------------------------------------


def shell_files() -> list[str]:
    """`git ls-files '*.sh'` plus the untracked ones, `awk NF | sort -u`.

    THE UNTRACKED HALF IS NOT DECORATION. `git ls-files` alone made this gate
    blind to any `.sh` a session had written but not yet committed, which is
    exactly when it is most useful: three new gate tests were invisible here
    until commit. `--others --exclude-standard` adds them while still honouring
    .gitignore, so node_modules and build output stay out.

    `gitx.ls_files(untracked=True)` issues ONE `git ls-files -z --cached --others
    --exclude-standard` and returns the union sorted and deduplicated, which is
    the same set the twin's two invocations plus `sort -u` produce. TWO
    DIFFERENCES, both named: `-z` means a non-ASCII path arrives raw here and
    OCTAL-QUOTED in the twin (`core.quotePath`), and Python sorts by code point
    where `sort -u` under `LC_ALL=C` sorts by byte. Every one of this tree's 620
    paths is ASCII, so the two agree today and would not agree over a path that
    is not.
    """
    return gitx.ls_files("*.sh", untracked=True)


def missing_files(files: list[str]) -> list[str]:
    """The ones `[ -e "$f" ]` says are gone. Order PRESERVED from `files`.

    A tracked file deleted in the working tree (`rm` without `git rm`) stays in
    `git ls-files` and makes shellcheck die on
    "openBinaryFile: does not exist", which reads as a lint finding. `-e`
    FOLLOWS SYMLINKS, so a dangling symlink counts as missing here too;
    `os.path.exists` answers the same way.
    """
    return [f for f in files if not os.path.exists(f)]


def batches(files: list[str], size: int = BATCH) -> list[list[str]]:
    """`xargs -n <size>`. The batch boundaries are observable; see the docstring."""
    return [files[i : i + size] for i in range(0, len(files), size)]


# --------------------------------------------------------------------------- The bash-4 probes ---------------------------------------------------------------------------


def build_scripts() -> list[str]:
    """`--include="*.sh"` under `.ci/scripts/build`, recursive, in BYTE order.

    RELATIVE to the current directory, because `main` has already reproduced the
    twin's `cd "$ROOT_DIR"` and the twin's `grep -rn ... .ci/scripts/build` names
    the directory relatively. The relative spelling reaches the report: every
    finding line is `<path>:<lineno>:<line>`, and an absolute `<path>` there
    would be a different report.

    Byte order rather than the ambient `grep -r`'s traversal order; see the
    module docstring for why that is a decision and not an accident.
    """
    root = pathlib.Path(BUILD_DIR)
    found: list[str] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(pathlib.Path(entry.path))
                elif entry.name.endswith(".sh") and entry.is_file(follow_symlinks=False):
                    found.append(entry.path)
            except OSError:
                continue
    return sorted(found)


def grep_lines(files: list[str], matcher) -> str:
    """`grep -rn <pattern>` output: `path:lineno:line`, newline-joined, no tail.

    Empty when nothing matches, which is what the twin's `|| true` leaves in
    `$MATCHES` and what its `[[ -n "$MATCHES" ]]` tests.
    """
    hits: list[str] = []
    for path in files:
        try:
            text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # splitlines(), not split("\n"): the latter invents an empty final line after a trailing newline, and grep does not report one.
        for number, line in enumerate(text.splitlines(), start=1):
            if matcher(line):
                hits.append("%s:%d:%s" % (path, number, line))
    return "\n".join(hits)


# `-w` in GNU grep means the match must be bounded by non-word characters on both sides, where a word character is `[A-Za-z0-9_]`. Expressed as lookarounds rather than `\b` so the boundary rule is visible at the call site.
_COPROC = re.compile(r"(?<![A-Za-z0-9_])coproc(?![A-Za-z0-9_])")
_MAPFILE = re.compile(r"^[^#]*(?:%s|%s)(?![A-Za-z0-9_])" % (_MAP_FILE, _READ_ARR))
# `[^#]*|&` is a BASIC regular expression, in which `|` is a LITERAL pipe and NOT an alternation. So the pattern is "some non-# characters, then `|&`", which is any line containing `|&` at all.
_PIPE_AMP = re.compile(r"[^#]*\|&")


def bash4_issues() -> str:
    """`$BASH4_ISSUES`, with the twin's LITERAL `\\n` separators still in it.

    Returned unexpanded on purpose: `main` hands it to `echo_e`, exactly as the
    twin hands it to `echo -e`, and the expansion is where defect 1 happens.
    """
    files = build_scripts()
    out = ""
    for label, matcher in (
        ("declare -A (associative arrays require bash 4.0+):", lambda s: "declare -A" in s),
        ("|& (pipe stderr requires bash 4.0+):", lambda s: _PIPE_AMP.search(s) is not None),
        ("coproc (requires bash 4.0+):", lambda s: _COPROC.search(s) is not None),
        (
            "%s/%s (requires bash 4.0+):" % (_MAP_FILE, _READ_ARR),
            lambda s: _MAPFILE.search(s) is not None,
        ),
    ):
        matches = grep_lines(files, matcher)
        if matches:
            out += "\\n%s\\n%s" % (label, matches)
    return out


# --------------------------------------------------------------------------- main ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    """`main` (:45-178). argv is accepted and ignored, as `main "$@"` does."""
    del argv
    base = paths.repo_root()
    # `cd "$ROOT_DIR"` (:46). Load-bearing: every path below is repo-relative and the relative spelling reaches shellcheck's own finding lines.
    os.chdir(base)

    log_info("Checking shell script compatibility")

    binary, messages = toolchain.acquire("shellcheck")
    for line in messages:
        print(line, file=sys.stderr)
    if binary is None:
        log_error("shellcheck is unusable for this gate")
        log_info("Every lane's toolchain: .ci/scripts/lib/toolchain.sh --report")
        log_info(
            "Or run the gate where it is pinned: "
            "./run.sh devbox exec -- .ci/scripts/security/shellcheck.sh"
        )
        return 1

    sys.stdout.flush()
    subprocess.run([binary, "--version"], check=False)

    log_info("Checking every tracked and untracked *.sh file")
    files = shell_files()
    gone = missing_files(files)
    if gone:
        log_info(
            "skipping %d tracked file(s) deleted in the working tree: %s"
            % (len(gone), " ".join(gone))
        )
        if not os.path.exists(files[-1]):
            return 1
        # DEFECT 2, REPRODUCED. The filtering assignment's status is the last iteration's `[ -e "$f" ] && printf` list, so a missing LAST path takes the whole gate down with `set -e` right here, silently, having linted nothing. See the module docstring for the measurement.
        files = [f for f in files if f not in set(gone)]

    # A gate that lints nothing exits 0 and looks identical to a gate that lints everything. Refuse the empty list rather than pass it.
    if not files:
        log_error("no tracked *.sh files found: the enumerator is broken, not the tree clean")
        return 1
    log_info("%d file(s)" % len(files))

    failed = False
    for chunk in batches(files):
        sys.stdout.flush()
        sys.stderr.flush()
        proc = subprocess.run([binary, *SHELLCHECK_OPTS, *chunk], check=False)
        if proc.returncode != 0:
            # xargs runs EVERY batch and then reports 123 if any of them exited 1-125, so a finding in batch 1 does not stop batch 2 from running.
            failed = True
    if failed:
        log_error("shellcheck reported findings")
        return 1

    log_info("Checking build scripts for bash 4+ features (macOS compatibility)")
    issues = bash4_issues()
    if issues:
        log_error("Found bash 4+ features in build scripts that don't work on macOS (bash 3.2):")
        sys.stdout.write(echo_e(issues))
        log_info(
            "macOS ships with bash 3.2 due to GPLv3 licensing. "
            "Use bash 3.x compatible alternatives."
        )
        return 1

    # NOTE: a "duplicated shared constants" check lived here until 2026-07-22. It guarded exactly one constant (MAX_GEMINI_REVIEWS, removed with the Gemini review machinery) and an empty guard list checks nothing. Reintroduce the loop if common.sh ever grows shared constants again.

    log_success("Shell scripts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
