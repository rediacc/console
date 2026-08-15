#!/usr/bin/env python3
"""Control harness for block-destructive-git-restore.sh.

BOTH DIRECTIONS, because a one-sided control is satisfiable by a broken hook:
one that always blocks passes every positive case, and one that never blocks
passes every negative case. Only the pair pins the behaviour.

The negative cases matter more than usual here. This guard sits on `git
checkout`, which sessions legitimately use to switch branches all day. A guard
that blocks that is one sessions will demand be removed, and then the tree has
no guard at all.
"""

import json
import pathlib
import subprocess
import sys

HOOK = pathlib.Path(__file__).with_name("block-destructive-git-restore.sh")

# MUST BLOCK: every one of these discards uncommitted work.
BLOCK = [
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
    # Prose mentioning the command must not trip it; hooks scan commands, and a
    # commit message or an echo is not an invocation.
    "echo 'never run git restore in a shared tree'",
]


def run(cmd: str) -> int:
    payload = json.dumps({"tool_input": {"command": cmd}})
    # check=False is explicit: this harness EXPECTS non-zero exits (a blocked
    # command is the hook working), so raising on them would invert the test.
    proc = subprocess.run(
        ["bash", str(HOOK)], input=payload, capture_output=True, text=True, check=False
    )
    return proc.returncode


def main() -> int:
    # Both directions in one pass: a command that must be BLOCKED (exit 2) and
    # one that must be ALLOWED (exit 0). Keeping them as comprehensions rather
    # than append-loops is what ruff's PERF401 asks for, and it keeps the two
    # halves of the control visibly symmetric.
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
