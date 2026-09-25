#!/usr/bin/env python3
"""Port of `.ci/scripts/security/check-commands.sh`.

Checks shell scripts for commands not reliably available in minimal CI environments (Ubuntu minimal, macOS, Windows Git Bash), complementing shellcheck (which does not know about runner-image gaps).

REGISTERED CI GATE: `check:ci-shell-commands`, `ci-quality.yml:351`.

PORT NOTES.

TWO REAL BUGS, FIXED 2026-09-10 IN THE TWIN AND HERE IN LOCKSTEP. Until this date, both the `$(` branch of the wide per-file filter and the narrow per-command check, and the narrow check's missing `if` branch, were dead code in both the twin and this port (deliberately reproduced here to stay byte-for-byte behind the still-buggy twin). The twin's source used to read `\\$\\(` inside
a double-quoted grep argument; bash's double-quote rules strip the backslash before `$` (one of the five characters double quotes treat specially) while leaving the backslash before `(` untouched, so the byte sequence grep actually received was `$\\(` -- an UNESCAPED `$` immediately followed by a literal `(`. `.ci` runs on ugrep (7.5.0 measured), whose `-E` mode treats that `$` as
a real end-of-line anchor even mid-pattern inside an alternation, exactly the class of silent breakage this repo's own house rule documents for an alternated `^` (`grep -cE '(^|[^a-z-])ease'` printing 0 where `-P` printed 26). An anchor that cannot be followed by anything within the same match makes the whole alternative unmatchable.

Consequence, before the fix: `x=$(shuf -n1 file.txt)` -- a disallowed command
hidden inside a command substitution -- was invisible to this gate. A SECOND, INDEPENDENT GAP: the narrow per-command check lacked the wide filter's `^[[:space:]]*if[[:space:]]+` branch entirely (four branches against five), so `if seq 1 10; then` passed the file-level candidate test but matched no per-command narrow regex and was never reported.

FIXED 2026-09-10: `.ci/scripts/security/check-commands.sh:70,84` now read `\\\\$\\(` (an escaped `$` that survives bash's double-quote stripping) and line 84 carries all five alternatives, matching line 70. This module's `_WIDE_RE`/`_narrow_re` mirror the same fix: `\\$\\(` (Python raw-string escaping, not bash quoting, but the identical effect -- `re.search(r"\\$\\(", "a$(b")`
matches where the old bare-`$` form did not). Applying the fix surfaced **46 real, previously-invisible findings** across the tracked corpus, verified live and all fixed in the same change (mostly
`for i in $(seq A B); do` loops rewritten to `for ((i=A; i<=B; i++)); do`,
plus a handful of non-mechanical padding-idiom and `timeout`/`set -e` rewrites -- see `agent/plans/PLAN-shell-command-gate-regex-fix.md` for the full list and the two subtler bugs a naive rewrite would have introduced). The real registered gate (`npm run check:ci-shell-commands`) is green against the fully-fixed tree.

CORPUS ENUMERATION USES `paths.walk_tree`, NOT A RAW `find` SHELL-OUT. It used to shell out to the real `find` binary so the twin's own unsorted, filesystem-dependent output ORDER would be reproduced exactly. The twin is gone (see above), so nothing depends on that order any more, and a raw `find <subdir> -name '*.sh'` walks `.ci/cache/` -- untracked build state (profiles, gate
durations, stamps, generated scratch) that CI never checks out. On 2026-09-24 that put a local run's `.ci/cache/w7p5a-realrun/.../run-stripe-e2e.sh` and several other cached copies of tracked scripts into this gate's corpus, reporting `seq`/`timeout`/`mapfile` findings CI could never see or fix. `paths.walk_tree` prunes `.ci/cache` (and `.claude/worktrees`, `.git`, `node_modules`)
the same way `rediacc_ci.security.shfmt.shell_files` already does, so both `*.sh` enumerators in this package now agree on what "the tree" means. Output is sorted for a deterministic order instead of an arbitrary one.

`[[:space:]]` IS TRANSLITERATED AS `[ \\t]`, not `\\s`, in the two branches that use it (`^[[:space:]]*`, `^[[:space:]]*if\\s+`). POSIX's space class includes more (`\\n \\v \\f \\r`), but these patterns run against single already-split lines with no embedded newline, so the only members that can ever appear are space and tab.

THE `---- gate ----` HEADER MOVED HERE when the twin was retired, the way `rediacc_ci.quality.staging_tag_guard` carries its own. `scripts/gate-bind.ts` resolves a gate by where its header lives, and with the bash file gone this is the one file that can own it; the `run:` was already the module form, which is what the binder emits into the workflow.

---- gate ----
step: Shell commands exist on the runner image
needs: none
run: PYTHONPATH=.ci python3 -m rediacc_ci.security.check_commands
id: check:ci-shell-commands
selftest: true
---- end gate ----
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from rediacc_ci import paths

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# (command, alternative) -- ORDER MATTERS: the narrow per-line check tries these in this exact order and reports (then breaks on) the FIRST one whose narrow regex matches a given line and is not skipped.
DISALLOWED: list[tuple[str, str]] = [
    ("bc", "awk 'BEGIN {printf \"%.2f\", x/y}'"),
    ("dc", "awk for calculations"),
    ("seq", "bash: for ((i=1; i<=n; i++)) or awk"),
    ("timeout", "not on macOS - use background + sleep + kill pattern"),
    ("readarray", "bash 4+ only - use while read loop"),
    ("mapfile", "bash 4+ only - use while read loop"),
    ("column", "not in minimal images - use printf with fixed widths"),
    ("numfmt", "GNU only - use awk"),
    ("shuf", "GNU only - use sort -R or awk"),
    ("tac", "GNU only - use tail -r (BSD) or awk"),
]

_CMD_ALTERNATION = "|".join(r"\b%s\b" % re.escape(cmd) for cmd, _alt in DISALLOWED)

# `(^[[:space:]]*|[|&;]\s*|\$\(|^[[:space:]]*if\s+)($pattern)`. Fixed 2026-09-10 in lockstep with the twin -- see module docstring.
_WIDE_RE = re.compile(r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)(" + _CMD_ALTERNATION + ")")


def _narrow_re(cmd: str) -> re.Pattern[str]:
    """`(^[[:space:]]*|[|&;]\\s*|\\$\\(|^[[:space:]]*if\\s+)${cmd}\\b`."""
    return re.compile(r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)" + re.escape(cmd) + r"\b")


def _assignment_skip_re(cmd: str) -> re.Pattern[str]:
    return re.compile(r"^\s*(local\s+|export\s+|readonly\s+)?" + re.escape(cmd) + "=")


_COMMENT_SKIP_RE = re.compile(r"^\s*#")


def _yaml_key_skip_re(cmd: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(cmd) + ":")


def _find_sh_files(root: Path, subdir: str) -> list[str]:
    """Every `*.sh` regular file under `root / subdir`, repo-relative and sorted. Walks with `paths.walk_tree`, which prunes `.ci/cache` (untracked build scratch, invisible to `git ls-files` and to every CI checkout, but not to a raw directory walk -- see the module docstring) along with `.claude/worktrees`, `.git` and `node_modules`. A missing directory yields no files, matching the twin's `2>/dev/null` swallow of a `find` failure."""
    start = root / subdir
    found: list[str] = []
    for dirpath, _dirnames, filenames in paths.walk_tree(start):
        for name in filenames:
            if not name.endswith(".sh"):
                continue
            candidate = Path(dirpath) / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            found.append(candidate.relative_to(root).as_posix())
    return sorted(found)


def _line_finding(line_content: str) -> tuple[str, str] | None:
    """Returns `(cmd, alt)` for the first disallowed command that fires on this line and is not skipped, or `None` if none does. Mirrors the twin's inner `for entry in DISALLOWED; do ... continue/break ... done` exactly: a narrow-regex match that is SKIPPED (comment/assignment/yaml-key) moves on to the NEXT disallowed command on the SAME line, it does not abandon the line."""
    for cmd, alt in DISALLOWED:
        if not _narrow_re(cmd).search(line_content):
            continue
        if _assignment_skip_re(cmd).search(line_content):
            continue
        if _COMMENT_SKIP_RE.search(line_content):
            continue
        if _yaml_key_skip_re(cmd).search(line_content):
            continue
        return cmd, alt
    return None


def _console_root() -> Path:
    # This file: <root>/.ci/rediacc_ci/security/check_commands.py
    return Path(__file__).resolve().parents[3]


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments
    root = _console_root()
    ci = os.environ.get("CI", "") == "true"
    red = "" if ci else RED
    green = "" if ci else GREEN
    nc = "" if ci else NC

    def log_error(msg: str) -> None:
        print(f"{red}error: {msg}{nc}", file=sys.stderr)

    def log_success(msg: str) -> None:
        print(f"{green}success: {msg}{nc}")

    def log_info(msg: str) -> None:
        print(f"info: {msg}")

    log_info("Checking shell scripts for CI-incompatible commands...")

    total_errors = 0

    scripts = [
        *_find_sh_files(root, ".ci"),
        *_find_sh_files(root, "scripts"),
        "./run.sh",
        "./rdc.sh",
    ]

    for script in scripts:
        path = root / script
        try:
            text = path.read_text(encoding="utf-8", errors="surrogateescape")
        except OSError:
            # `2>/dev/null` on the per-file grep in the twin: an unreadable or missing file (e.g. `./run.sh` when it does not exist) yields no matches, not an error.
            continue

        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]

        for line_num, line_content in enumerate(lines, start=1):
            if not _WIDE_RE.search(line_content):
                continue
            finding = _line_finding(line_content)
            if finding is None:
                continue
            cmd, alt = finding
            log_error(f"{script}:{line_num}: '{cmd}' not available in minimal CI")
            print(f"  Line: {line_content}")
            print(f"  Fix:  {alt}")
            print()
            total_errors += 1

    if total_errors > 0:
        print()
        log_error(f"Found {total_errors} CI-incompatible command(s)")
        log_info("These commands may not be available in ubuntu-slim or other minimal CI images")
        return 1

    log_success("All commands are CI-compatible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
