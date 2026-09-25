#!/usr/bin/env python3
"""Control harness for block-destructive-git-restore.sh.

BOTH DIRECTIONS, because a one-sided control is satisfiable by a broken hook: one that always blocks passes every positive case, and one that never blocks passes every negative case. Only the pair pins the behaviour.

The negative cases matter more than usual here. This guard sits on `git checkout`, which sessions legitimately use to switch branches all day. A guard that blocks that is one sessions will demand be removed, and then the tree has no guard at all.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

# THIS HARNESS SITS BESIDE ITS GUARD, which is what .ci/scripts/quality/check-hook-integrity.sh means by a dedicated test file: `test-<stem>.py` next to `<stem>.py` credits the guard with BOTH directions, and it is the only credit these four have because their block direction needs fixture work `test-hooks.sh`'s one-line `check` helper cannot express.
#
# THE GUARD IS A PYTHON MODULE NOW. W5 P7 ported it from a bash original that PLAN-retire-bash-oracles A3 later deleted, once the differential compared the two byte for byte and froze the result as a golden (tests/goldens/<stem>.jsonl). This harness drives the LIVE guard, which is the dispatcher, for the reason the cutover exists at all: a suite that kept driving the retired file would keep passing while the thing that actually runs went unchecked. A REAL
# FOREIGN REPOSITORY, built rather than named. The scope cases below assert that the guard stands down outside this checkout, and `target_root` resolves a path by asking git about it: a path that does not exist is unresolvable, the guard keeps guarding by design, and the case would then pass only while the fixture was missing -- green for the opposite of the reason it claims.
# Measured on the first run of these two cases, which failed against a made-up /tmp path.
# `rediacc_ci.runtmp`, loaded BY FILE rather than through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those): a pid-stamped run directory, removed at exit and swept by the next run when this one was killed before `atexit` could fire, which is how /tmp hit its inode cap on 2026-09-24.
_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-scope-")
_FOREIGN_DIR = tempfile.mkdtemp(prefix="foreign-", dir=RUN_TMP)
subprocess.run(["git", "init", "-q", _FOREIGN_DIR], check=True, capture_output=True)
pathlib.Path(_FOREIGN_DIR, "a.txt").write_text("hi\n", encoding="utf-8")

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_destructive_git_restore"]

# MUST BLOCK: every one of these discards uncommitted work.
BLOCK = [
    # A SUBMODULE is a different git toplevel and is NOT foreign: private/account is shared and frozen, so a discard there is exactly what this guard refuses. Pinned because the scope fix above allowed it until the predicate was narrowed from "different toplevel" to "outside the project tree".
    "git -C private/account restore .",
    "git checkout -- packages/www/src/i18n/translations/.translation-hashes.json",  # the real 2026-08-14 command
    "git checkout --",
    "git checkout .",
    "git checkout -- .",
    "git checkout HEAD -- src/file.ts",
    "git restore src/file.ts",
    "git restore --staged --worktree .",
    "git -C private/renet restore pkg/chunkstore/session.go",
    "git stash",
    "git stash push -m wip",
    "git stash pop",
    "git clean -fd",
    "git clean -fdx packages/",
    "cd /tmp && git checkout -- foo.txt",  # after a ;/&& chain
    "echo hi; git restore src/",  # command position after ;
]

# MUST NOT BLOCK: branch work, read-only inspection, and unrelated commands.
ALLOW = [
    # SCOPE, added 2026-09-09: a repo that is not this worktree. The guard's argument is about THIS shared checkout, and a session's throwaway fixture repo is not it. The first cut of this keyed on the event's cwd and could never fire, because the harness resets the shell's directory after every call -- the directory that matters is the one spelled in the command.
    "git -C %s restore ." % _FOREIGN_DIR,
    "git -C %s checkout -- ." % _FOREIGN_DIR,
    "git checkout main",
    "git checkout -b feature/x",
    "git checkout -B backup-storage origin/main",
    "git checkout backup-storage",
    "git stash list",
    "git stash show -p",
    "git clean -n",
    "git clean --dry-run -fd",
    "git status",
    "git diff -- packages/www",
    "git add -- src/file.ts",
    "npm run check:i18n",
    # Prose mentioning the command must not trip it; hooks scan commands, and a commit message or an echo is not an invocation.
    "echo 'never run git restore in a shared tree'",
]


def run(cmd: str) -> int:
    payload = json.dumps({"tool_input": {"command": cmd}})
    # check=False is explicit: this harness EXPECTS non-zero exits (a blocked
    # command is the hook working), so raising on them would invert the test.
    proc = subprocess.run(GUARD_ARGV, input=payload, capture_output=True, text=True, check=False)
    return proc.returncode


def main() -> int:
    # Both directions in one pass: a command that must be BLOCKED (exit 2) and one that must be ALLOWED (exit 0). Keeping them as comprehensions rather than append-loops is what ruff's PERF401 asks for, and it keeps the two halves of the control visibly symmetric.
    failures = [f"MUST BLOCK but did not: {cmd!r}" for cmd in BLOCK if run(cmd) != 2]
    failures += [f"MUST ALLOW but blocked: {cmd!r}" for cmd in ALLOW if run(cmd) != 0]

    if failures:
        print(f"✗ block-destructive-git-restore: {len(failures)} control failure(s)")
        for f in failures:
            print(f"    {f}")
        return 1

    print(
        f"✓ block-destructive-git-restore: {len(BLOCK)} blocked, {len(ALLOW)} allowed "
        "(both directions pinned)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
