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
    "git stash drop",
    "git stash clear",
    "git clean -fd",
    "git clean -fdx packages/",
    "cd no-such-subdir && git checkout -- foo.txt",  # after a ;/&& chain
    "echo hi; git restore src/",  # command position after ;
    # #18c7e53c (operator ruling 2026-10-09: /branch-rebase is AI-invocable, and a guard covers what its prose forbids). Every one of these answered rc 0 through the live pre-bash chain in the audit that opened the item.
    "git checkout -f",
    "git checkout -f main",
    "git -C private/renet checkout --force HEAD",
    "git checkout HEAD packages/cli/x.ts",  # a tree-ish and a path, no `--`
    "git checkout origin/main packages/cli/x.ts",
    # A lone operand that resolves as no ref is a PATHSPEC to git. Until #18c7e53c this name sat in ALLOW as "branch switching", which it is only in a checkout that has the branch; here it has none, so git would read it as a path.
    "git checkout backup-storage",
    "git switch -f main",
    "git switch --discard-changes main",
    "git checkout --ours private/renet",
    "git checkout --theirs private/renet",
    "git reset --hard",
    "git reset --hard origin/main",
    "git -C private/renet reset --hard origin/main",
    "git reset --merge",
    "git reset --keep HEAD",
    "git rebase --autostash origin/main",
    "git -c rebase.autoStash=true rebase origin/main",
    "git -c rebase.autostash=true pull --rebase",
    "git pull --rebase --autostash",
    "git merge --autostash origin/main",
    "git config rebase.autoStash true",
    "git config --global rebase.autoStash true",
    "git -C private/renet pull --rebase --autostash",
    # #a234b06e, the second widening: each lost a modified or staged file in a measured scratch fixture (the guard's docstring has the table).
    "git rm -f packages/cli/x.ts",
    "git -C private/renet rm -rf pkg",
    "git rm --cached -r .",
    "git rm --cached '*.ts'",
    "git read-tree --reset -u HEAD",
    "git read-tree -m -u HEAD",
    "git read-tree --empty",
    "git checkout-index -f -a",
    "git mv -f a.txt b.txt",
    "git submodule update --init --force",
    "git submodule update -f",
    "git submodule deinit -f private/renet",
    "git submodule--helper update --force",
    "git submodule foreach git clean -fd",
    "git submodule foreach 'git stash; git status'",
    "git submodule foreach --recursive git reset --hard",
    "git -C private/renet submodule foreach git checkout -- .",
    "cd private/renet && git submodule foreach git rm -f x",
    # A wide write in a foreach payload reaches this checkout from a foreign repository's submodules too.
    "git -C %s submodule foreach git config --global rebase.autoStash true" % _FOREIGN_DIR,
    # Review 9849764b.1: a payload's `-C` is relative to the SUBMODULE it runs in, so `../..` from private/renet is this checkout. It was resolved from the project root instead, landed outside the tree, and the guard stood down.
    "git submodule foreach git -C ../.. reset --hard",
    "git -C private/renet submodule foreach 'git -C ../.. checkout -- .'",
    # Review 72e7ac97.2: GIT_CONFIG_PARAMETERS is parsed per key, so a true value still refuses, in any case and beside other keys.
    "GIT_CONFIG_PARAMETERS=\"'rebase.autostash'='true'\" git rebase origin/main",
    "GIT_CONFIG_PARAMETERS=\"'user.x'='1' 'Merge.AutoStash'='yes'\" git merge origin/main",
    "GIT_CONFIG_PARAMETERS=\"'rebase.autostash'\" git rebase origin/main",
]

# MUST NOT BLOCK: branch work, read-only inspection, and unrelated commands.
ALLOW = [
    # SCOPE, added 2026-09-09: a repo that is not this worktree. The guard's argument is about THIS shared checkout, and a session's throwaway fixture repo is not it. The first cut of this keyed on the event's cwd and could never fire, because the harness resets the shell's directory after every call -- the directory that matters is the one spelled in the command.
    "git -C %s restore ." % _FOREIGN_DIR,
    "git -C %s checkout -- ." % _FOREIGN_DIR,
    "git checkout main",
    "git checkout -b feature/x",
    "git checkout -B backup-storage origin/main",
    # #18c7e53c's allow half: a lone operand that RESOLVES is a switch, and the /branch-rebase steps stay open.
    "git checkout HEAD",
    "git checkout --detach HEAD",
    "git -C private/renet checkout HEAD",
    "git switch main",
    "git reset --soft HEAD~1",
    "git reset --mixed",
    "git reset -- packages/cli/x.ts",
    "git rebase origin/main",
    "git rebase --no-autostash origin/main",
    "git -c rebase.autostash=false rebase origin/main",
    "git config rebase.autoStash false",
    # Review 72e7ac97.2/.3, measured on git 2.53.0 with `git config --type=bool`: a false value, an EMPTY value and an unrelated key that merely contains the word all read as no autostash.
    "GIT_CONFIG_PARAMETERS=\"'rebase.autostash'='false'\" git rebase origin/main",
    "GIT_CONFIG_PARAMETERS=\"'foo.autostash-note'='x'\" git rebase origin/main",
    "GIT_CONFIG_PARAMETERS=\"'rebase.autostash'=''\" git rebase origin/main",
    "git -c rebase.autostash= rebase origin/main",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=rebase.autostash GIT_CONFIG_VALUE_0= git rebase origin/main",
    # The allow half of 9849764b.1: a payload whose `-C` leaves the project tree from the submodule is still foreign.
    "git submodule foreach git -C %s reset --hard" % _FOREIGN_DIR,
    "git rebase --continue",
    "git rebase --abort",
    # #a234b06e's allow half: git refuses each of these over uncommitted work by itself, and /pr-merge runs the submodule update.
    "git rm packages/cli/x.ts",
    "git rm --cached packages/cli/x.ts",
    "git rm -rf -n packages",
    "git read-tree -n --reset -u HEAD",
    "git checkout-index -a",
    "git checkout-index -f -a --prefix=/tmp/export/",
    "git mv a.txt b.txt",
    "git submodule update --init --recursive",
    "git submodule update --forc",
    "git submodule deinit private/renet",
    "git submodule foreach git status",
    "git submodule foreach 'git fetch origin --prune'",
    "git submodule foreach -- git clean -fd",
    "git -C %s submodule update --force" % _FOREIGN_DIR,
    "git -C %s submodule foreach git clean -fd" % _FOREIGN_DIR,
    "git stash list",
    "git stash show -p",
    "git stash create",  # writes a dangling commit only
    "git stash store 0123abc",  # records an existing commit in the reflog only
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
