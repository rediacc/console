"""Port of `.claude/lib/standing-orders-brief.sh` (120 lines).

The live-state brief printed by the `/standing-orders` slash command: who I am, my open worklist slice, the ownership split against peer sessions, whether my `[>]` leases are believable, what peers are waiting on, and the durable context under `agent/`.

LIVE CALLER OF THE TWIN, not repointed by this port:
  * `.claude/commands/standing-orders.md:10` -- the `!`bash
    .claude/lib/standing-orders-brief.sh`` block that renders the command.
  * `.claude/commands/standing-orders.md:5` -- `allowed-tools: Bash(bash
    .claude/lib/standing-orders-brief.sh)`, which pins the exact command STRING
    the permission matcher will accept. Repointing the caller therefore means
    editing two lines that must stay in lockstep, and it is not this port's job.

READ-ONLY BY CONSTRUCTION, on both sides. Nothing here writes to the worklist store; `worklist.py` is invoked only with `--list` and `--poll`.

EVERY PATH IS RELATIVE TO THE PROCESS'S CURRENT DIRECTORY, deliberately. The twin uses `.claude/hooks/stop/worklist.py`, `agent/...` and a bare `pwd`, so it reports on whatever checkout it is run from. `paths.repo_root()` is NOT used: that resolver honours $REDIACC_CI_ROOT and would make the port describe a different tree from the twin when the two are compared side by side.

PORT NOTES, each driven before it was written down.

*** A REAL DEFECT IN THE TWIN, REPRODUCED RATHER THAN FIXED ***
`standing-orders-brief.sh:21` is `ME="${CLAUDE_CODE_SESSION_ID:0:8}"` under
`set -u` (:18). When the variable is entirely UNSET -- not empty, UNSET -- the substring expansion is an unbound-variable error, and a non-interactive bash EXITS on it. So the friendly guard on :27-31, whose whole purpose is to explain that case, is DEAD CODE for it: it is reachable only when the variable is set to the empty string. Driven, twice:
  `bash -c 'set -uo pipefail; X="${NOPE:0:8}"; echo REACHED'`
      -> `bash: NOPE: unbound variable`, nothing on stdout
  `env -u CLAUDE_CODE_SESSION_ID bash .claude/lib/standing-orders-brief.sh`
      -> `line 21: CLAUDE_CODE_SESSION_ID: unbound variable`, rc=1
This port exits 1 for the unset case, prints a one-line diagnostic naming the same variable, and does NOT forge bash's `line 21:` prefix -- a hard-coded line number in a port goes stale the first time the twin gains a comment. `test_review_standing_orders_brief.py` pins both halves.

*** A SECOND, COSMETIC DEFECT, ALSO REPRODUCED *** `:70` harvests worker ids with `grep -o 'worker:[A-Za-z0-9._-]*'` over the worklist's own output. That output contains the ADVICE string `... or re-lease: --lease <me> <id> +60 worker:<bg-id>`, whose `<` is outside the character class, so the match is the bare token `worker:` with an EMPTY id. The brief then reports a phantom lease
with no name. Observed live in this checkout on 2026-09-10: the section listed `worker:` above the one real `worker:ace7d3b020df07b32`. Reproduced exactly, including the empty id's
`${tasks_dir}/.output` probe path.

`stat | cut || echo MISSING` IS SAVED BY `pipefail`, AND ONLY BY IT. `:107` is
`state_age=$(stat -c %y ... 2>/dev/null | cut -d. -f1 || echo 'MISSING')`. The
`||` binds to the PIPELINE, and `cut` on empty input succeeds, so without `set -o pipefail` (:18) the fallback would never fire and `state_age` would be the empty string -- which would also disarm the anti-vacuity check on :116 that tests it against the literal `MISSING`. Driven both ways:
  `bash -c 'set -uo pipefail; v=$(stat -c %y /nope 2>/dev/null | cut -d. -f1 || echo MISSING); echo "[$v]"'` -> `[MISSING]`
  `bash -c 'set -u;           v=$(stat -c %y /nope 2>/dev/null | cut -d. -f1 || echo MISSING); echo "[$v]"'` -> `[]`
The port implements the pipefail-correct behaviour, which is what the twin does today, and `test_state_age_missing_is_really_reported` pins it.

`sort -u` IS SHELLED OUT TO, NOT REIMPLEMENTED. `sorted()` is byte order;
`sort -u` follows the collation of whatever locale the operator's terminal is in, and glibc's en_US.UTF-8 does not order `.`/`_`/`-` at the primary level. Worker ids are lowercase hex today so the two agree, but a port that quietly depended on that would diverge the first time an id carried a separator. One subprocess buys exactness.

`head -60` / `head -30` ARE LINE TRUNCATIONS, not byte ones, and the twin merges stderr into stdout BEFORE the pipe (`2>&1 | head`), so a worklist traceback is part of what gets truncated. Reproduced with a combined capture.

Exit: 0 always on the reachable paths, 1 for the unset-session-id death above.
"""

from __future__ import annotations

import datetime
import os
import pathlib
import re
import subprocess
import sys
import time

WL = ".claude/hooks/stop/worklist.py"

# `grep -o 'worker:[A-Za-z0-9._-]*'`. Explicit ASCII ranges, matching the twin's bracket expression under the C collation CI and the shadow-gate harness set.
WORKER_RE = re.compile(r"worker:[A-Za-z0-9._-]*")

# `grep -c '^ - \['` and `grep -c '^ - \[?\]'`. In a BRE `\[` and `\]` are literal brackets and `?` is an ordinary character, so the second pattern is the literal text ` - [?]` anchored at the start of a line.
OPEN_ITEM_PREFIX = "  - ["
DEFERRAL_PREFIX = "  - [?]"

COLD_MINUTES = 15


def _run(cmd: list[str], *, merge_stderr: bool = False) -> tuple[int, str]:
    """Run `cmd`, returning `(rc, output)`. A missing binary is bash's 127."""
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL,
            text=True,
        )
    except FileNotFoundError:
        return 127, ""
    return proc.returncode, proc.stdout


def head(text: str, n: int) -> str:
    """`head -n`: the first `n` lines, keeping their terminators as they were."""
    lines = text.splitlines(keepends=True)
    return "".join(lines[:n])


def count_lines_with_prefix(text: str, prefix: str) -> int:
    """`grep -c '<anchored literal>'`: the number of MATCHING LINES."""
    return sum(1 for line in text.splitlines() if line.startswith(prefix))


def sort_unique(lines: list[str]) -> list[str]:
    """`sort -u`, run as the real `sort` for the reason in the module docstring."""
    if not lines:
        return []
    try:
        proc = subprocess.run(
            ["sort", "-u"],
            check=False,
            input="\n".join(lines) + "\n",
            stdout=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return sorted(set(lines))
    return [line for line in proc.stdout.split("\n") if line != ""]


def mangle_cwd(cwd: str) -> str:
    """`pwd | tr -c 'A-Za-z0-9\\n' '-'`: every byte outside the keep set becomes a dash. The newline is IN the keep set, which is why it survives `tr` and is then stripped by the command substitution rather than becoming a dash."""
    return "".join(ch if (ch.isascii() and ch.isalnum()) else "-" for ch in cwd)


def resolve_tasks_dir(me: str, cwd: str) -> str:
    """The twin's :62-68. Empty string when nothing matches, as `tasks_dir=""`."""
    root = pathlib.Path(
        "%s/claude-%d/%s" % (os.environ.get("TMPDIR") or "/tmp", os.getuid(), mangle_cwd(cwd))
    )
    if not root.is_dir():
        return ""
    # `for d in "$root"/"$ME"*` iterates in the shell's glob order, which is the collation order of the current locale; `break` on the FIRST match makes that order load-bearing. `sorted()` is byte order, which is what bash's glob gives under the C collation this runs in.
    for d in sorted(root.glob("%s*" % me)):
        if (d / "tasks").is_dir():
            return str(d / "tasks")
    return ""


def _stat_size(path: pathlib.Path) -> int:
    """`stat -Lc %s "$f" 2>/dev/null || echo 0`, follow-symlink."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _stat_mtime(path: pathlib.Path) -> float:
    """`stat -Lc %Y "$f" 2>/dev/null || date +%s`, follow-symlink."""
    try:
        return path.stat().st_mtime
    except OSError:
        return time.time()


def _floor_div(numerator: int, denominator: int) -> int:
    """Bash `$(( a / b ))` TRUNCATES TOWARD ZERO; Python `//` floors. They differ
    for a negative numerator, which happens when a task's output file carries a
    future mtime (a clock skew across a container boundary is enough)."""
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments

    raw = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if raw is None:
        # THE UNSET CASE. See the module docstring: the twin dies here under `set -u` before its own guard can run, and the guard below is unreachable for it. bash's own `line 21:` prefix is not forged.
        print(
            "standing-orders-brief: CLAUDE_CODE_SESSION_ID: unbound variable",
            file=sys.stderr,
            flush=True,
        )
        return 1
    me = raw[:8]

    if me == "":
        print(
            "  (no CLAUDE_CODE_SESSION_ID in this environment: cannot tell my items from a peer's.",
            flush=True,
        )
        print("   Every count below would be a guess, so none are printed.)", flush=True)
        return 0

    rc, branch_out = _run(["git", "branch", "--show-current"])
    # `$(git ... 2>/dev/null || echo '?')`: the fallback fires on a NON-ZERO status, not on empty output. A detached HEAD prints nothing and exits 0, so the branch renders empty rather than as `?`.
    branch = branch_out.rstrip("\n") if rc == 0 else "?"
    stamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%dT%H:%MZ")
    print("I am %s on branch %s at %s" % (me, branch, stamp), flush=True)
    print(flush=True)  # the twin's bare `echo ""`

    print(
        "MY OPEN SLICE (the verb printed per item is the next command; "
        "base your report on this, not on memory):",
        flush=True,
    )
    _, mine_raw = _run(["python3", WL, "--list", "--open", me], merge_stderr=True)
    sys.stdout.write(head(mine_raw, 60))
    sys.stdout.flush()
    print(flush=True)  # the twin's bare `echo ""`

    _, all_raw = _run(["python3", WL, "--list", "--open"])
    _, mine_quiet = _run(["python3", WL, "--list", "--open", me])
    all_open = count_lines_with_prefix(all_raw, OPEN_ITEM_PREFIX)
    mine_open = count_lines_with_prefix(mine_quiet, OPEN_ITEM_PREFIX)
    deferrals = count_lines_with_prefix(mine_quiet, DEFERRAL_PREFIX)
    print(
        "OWNERSHIP: %d open in this repo, %d mine, %d a peer session's."
        % (all_open, mine_open, all_open - mine_open),
        flush=True,
    )
    print(
        "  The hook blocks only on mine. A peer's items are REPORTED to the "
        "operator and never worked, never ticked.",
        flush=True,
    )
    print(
        "OPEN DEFERRALS OF MINE: %d. A queue of these is over-asking, not a backlog:" % deferrals,
        flush=True,
    )
    print(
        "  anything settleable from the code, the request, or a sensible "
        "default was mine to decide.",
        flush=True,
    )
    print(flush=True)  # the twin's bare `echo ""`

    print("ARE MY [>] LEASES BELIEVABLE:", flush=True)
    tasks_dir = resolve_tasks_dir(me, os.getcwd())
    workers = sort_unique(WORKER_RE.findall(mine_quiet))

    if not workers:
        print("  (none: no in-flight background work claimed by me)", flush=True)
    elif tasks_dir == "":
        print(
            "  Cannot resolve this session's task directory, so no lease can be checked.",
            flush=True,
        )
        print("  Treat every [>] below as UNVERIFIED and probe before believing it.", flush=True)
        for worker in workers:  # `sed 's/^/    /'`
            print("    %s" % worker, flush=True)
    else:
        now = int(time.time())
        for worker in workers:
            ident = worker[len("worker:") :]
            path = pathlib.Path(tasks_dir) / ("%s.output" % ident)
            if path.exists():
                size = _stat_size(path)
                mins = _floor_div(now - int(_stat_mtime(path)), 60)
                print("    %s: %d bytes, last grew %dm ago" % (ident, size, mins), flush=True)
                if size == 0 and mins >= COLD_MINUTES:
                    print(
                        "      ^ empty and cold. Probe the process before trusting this lease;",
                        flush=True,
                    )
                    print("        an entry can outlive the worker that made it.", flush=True)
            else:
                print("    %s: no output stream this session can see." % ident, flush=True)
                print(
                    "      An Agent's NAME is not a background task id, and a "
                    "task started after the",
                    flush=True,
                )
                print(
                    "      last sidecar snapshot is legitimately absent. Probe, "
                    "do not assume death.",
                    flush=True,
                )
    print(flush=True)  # the twin's bare `echo ""`

    print("WAITING FOR ME FROM PEER SESSIONS (silence means nothing is waiting):", flush=True)
    _, poll_raw = _run(["python3", WL, "--poll", me], merge_stderr=True)
    sys.stdout.write(head(poll_raw, 30))
    sys.stdout.flush()
    print(flush=True)  # the twin's bare `echo ""`

    state_age = _state_age(pathlib.Path("agent") / me / "STATE.md")
    plans = (
        len(sorted(pathlib.Path("agent").glob("PLAN-*.md")))
        if pathlib.Path("agent").is_dir()
        else 0
    )
    peers = _peer_dirs(me)
    print(
        "DURABLE CONTEXT: my STATE.md %s; %d plan file(s) under agent/" % (state_age, plans),
        flush=True,
    )
    print(
        "  %d peer session folder(s) beside mine under agent/. Theirs to write, mine to read."
        % peers,
        flush=True,
    )
    print(
        "  These survive a reboot. The worklist event log is tracked under "
        "agent/worklist/ and survives too; only locks, caches and briefs live "
        "under $TMPDIR.",
        flush=True,
    )
    if plans == 0 or state_age == "MISSING":
        session_dirs = _session_dirs()
        print("  ^ SUSPECT: agent/ holds %d session dir(s) and" % session_dirs, flush=True)
        print(
            "    %d PLAN file(s). A zero here usually means this" % plans,
            flush=True,
        )
        print(
            "    brief is looking in the wrong place, not that the context is empty.",
            flush=True,
        )
    return 0


def _state_age(path: pathlib.Path) -> str:
    """`stat -c %y <path> | cut -d. -f1 || echo MISSING`, under `pipefail`.

    `%y` is a local-time timestamp `YYYY-MM-DD HH:MM:SS.nnnnnnnnn +ZZZZ`; `cut` takes everything before the first `.`.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return "MISSING"
    return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ006


def _peer_dirs(me: str) -> int:
    """`find agent -mindepth 1 -maxdepth 1 -type d ! -name "$ME" 2>/dev/null | wc -l`."""
    agent = pathlib.Path("agent")
    if not agent.is_dir():
        return 0
    return sum(1 for child in agent.iterdir() if child.is_dir() and child.name != me)


def _session_dirs() -> int:
    """`ls -1d agent/*/ 2>/dev/null | wc -l`: the shell glob `agent/*/` matches directories only, and skips dotted names."""
    agent = pathlib.Path("agent")
    if not agent.is_dir():
        return 0
    return sum(1 for child in agent.iterdir() if child.is_dir() and not child.name.startswith("."))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
