"""Block the four commands that DISCARD uncommitted work: `git checkout <path>`,
`git restore`, `git stash`, `git clean`.

WHY. This checkout is shared by several live sessions and the deliverable is
an UNCOMMITTED working tree, so there is no safety net underneath these. They
do not undo "your" change to a file, they discard every uncommitted change to
it, including work you cannot see and did not write.

WHY A HOOK AND NOT A RULE. CLAUDE.md session default 1 has said "never
checkout/restore/stash/clean to undo your own mistake" for months, in the same
paragraph that says the tree usually holds other sessions' work. On 2026-08-14
a locale writer read that rule, then ran `git checkout --` on a single file to
tidy up something a script had touched, and destroyed another session's
uncommitted value in it. The rule was not misunderstood; it was not recalled
at the one second it mattered. That is what a hook is for.

THE PART THAT MAKES THIS CLASS SILENT, and why the block is worth the friction:
the writer then checked `git status`, saw the file CLEAN, and sincerely
reported "touched then restored, net no-op". After an unwanted edit, clean
vs HEAD is the WRONG target. The right target is "identical to what was there
before I arrived", and the two coincide only in a tree with no uncommitted
work, which is never true here. The command had reset PAST the prior state, so
the file looked cleaner than correct. See docs/agent-reference/TRAPS.md, "Clean vs HEAD
is the wrong baseline in a tree that was already dirty".

WHAT TO DO INSTEAD: repair forward. Edit the value back to what it should be.
That keeps every other change in the file, including the ones you cannot see.
If a script touched a file you did not intend, say so and name the exact diff;
a reviewer can then decide, which is what happened above and is the only
reason the byte was recoverable at all.

DELIBERATELY NOT BLOCKED, because these do not discard anything:
  - `git checkout <branch>` / `-b` / `-B`: branch switching and creation.
    Only PATH-scoped checkout discards.
  - `git stash list` / `show`: read-only.
  - `git clean -n` / `--dry-run`: prints what it would remove.
The escape for a genuine need is a human: ask the operator, who can run it
themselves with the `!` prefix and knows what else is in the tree.

NO CROSS-TALK with block-protected-files.sh, which blocks restore/checkout/rm
aimed at the hook files specifically. This guard is about the shared tree in
general; that one is about protecting the guards themselves. Both may match a
single command, which is fine: the first to fire wins and both messages are
true.

PORT NOTE ON THE SIX SEQUENTIAL TESTS. The bash runs all six greps
unconditionally and lets each one OVERWRITE `BLOCKED`, so the message names
the LAST shape that matched and not the first. `git stash pop && git clean -f`
is reported as `git clean`. That is behaviour, not an accident of layout, so
the loop below assigns in the same order rather than returning early.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-destructive-git-restore.sh"
ORDER = 31

# `git clean -n` and `--dry-run` PRINT what they would remove and delete
# nothing. Dropping the exclusion turns the one safe way to inspect the
# untracked set into a refusal, which is how this guard would start being
# routed around.
DEFECT = ("and not hookio.grep_q(DRY_RUN, scan)", "and True")

# Command position: line start, or after ; & | ( $( or a backtick. Flags between
# `git` and the verb (-C <path>, -c k=v) stay matched: they change where the
# command runs, not what it destroys.
GIT = (
    r"(^|[;&|(]|\$\(|`)["
    + hookio.SPACE
    + r"]*git(["
    + hookio.SPACE
    + r"]+-[A-Za-z-]+(["
    + hookio.SPACE
    + r"]+[^ ;&|]+)?)*["
    + hookio.SPACE
    + r"]+"
)

# `git restore ...` always discards (worktree by default, index with --staged).
RESTORE = GIT + r"restore([" + hookio.SPACE + r"]|$)"

# Bare `git stash` (stashes everything) OR an explicitly mutating subcommand.
# `list` and `show` must NOT match, so the verb cannot be a bare wildcard: an
# earlier draft made it optional, which swallowed `git stash list` and the
# control harness caught it immediately.
STASH_BARE = GIT + r"stash[" + hookio.SPACE + r"]*($|[;&|])"
STASH_VERB = (
    GIT
    + r"stash["
    + hookio.SPACE
    + r"]+(push|save|pop|apply|drop|clear|branch|create|store)(["
    + hookio.SPACE
    + r"]|$)"
)

# `git clean` deletes UNTRACKED files, which in this repo includes entire
# packages (pkg/chunkstore is untracked in its entirety). Excluded when -n or
# --dry-run appears anywhere in the invocation.
CLEAN = GIT + r"clean([" + hookio.SPACE + r"]|$)"
DRY_RUN = r"(^|[" + hookio.SPACE + r"])(-n|--dry-run)([" + hookio.SPACE + r"]|$)"

# `git checkout` ONLY when path-scoped: an explicit `--`, or a `.`/`:/` pathspec.
# Bare `git checkout <branch>` and `-b <new>` are untouched.
CHECKOUT_DDASH = (
    GIT
    + r"checkout(["
    + hookio.SPACE
    + r"]+[^;&|]*)?["
    + hookio.SPACE
    + r"]+--(["
    + hookio.SPACE
    + r"]|$)"
)
CHECKOUT_DOT = (
    GIT
    + r"checkout(["
    + hookio.SPACE
    + r"]+-[A-Za-z-]+)*["
    + hookio.SPACE
    + r"]+(\.|:/)(["
    + hookio.SPACE
    + r"]|$)"
)

MESSAGE = (
    "❌ BLOCKED: `%s` DISCARDS uncommitted work, and this checkout is shared by several live "
    "sessions whose work is also uncommitted. It does not undo your change to a file, it "
    "discards EVERY uncommitted change to it. On 2026-08-14 exactly this command, aimed at "
    "one file to tidy up a stray edit, destroyed another session's value; the author then "
    "saw a clean `git status` and sincerely reported it as a no-op, because after an "
    'unwanted edit "clean vs HEAD" is the wrong target and "identical to what was there '
    'before I arrived" is the right one. REPAIR FORWARD instead: edit the value back, which '
    "keeps every other change in the file including the ones you cannot see. If a script "
    "touched something you did not intend, say so and name the exact diff rather than "
    "erasing it. If you genuinely need this command, ask the operator to run it with the `!` "
    "prefix; they know what else is in the tree. Read-only forms are allowed: `git stash "
    "list`, `git stash show`, `git clean -n`, and branch switching (`git checkout <branch>`, "
    "`-b`) are not blocked."
)

EDGE_CASES = [
    ("a restore", "git restore packages/cli/src/x.ts"),
    ("a bare stash", "git stash"),
    ("a mutating stash verb", "git stash pop"),
    ("a clean", "git clean -fd"),
    ("a path-scoped checkout", "git checkout -- packages/www/src/i18n/translations/de.json"),
    ("a dot pathspec checkout", "git checkout ."),
    # The read-only forms, which are the whole reason the verb cannot be a
    # bare wildcard.
    ("stash list is read-only", "git stash list"),
    ("stash show is read-only", "git stash show"),
    ("clean -n prints what it would remove", "git clean -n"),
    ("clean --dry-run does the same", "git clean --dry-run"),
    ("branch switching is untouched", "git checkout main"),
    ("branch creation is untouched", "git checkout -b 0901-1"),
    # The last match wins, which is why the message can name `git clean`.
    ("two destructive verbs on one line", "git stash pop && git clean -fd"),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    blocked = ""
    if hookio.grep_q(RESTORE, scan):
        blocked = "git restore"
    if hookio.grep_q(STASH_BARE, scan):
        blocked = "git stash"
    if hookio.grep_q(STASH_VERB, scan):
        blocked = "git stash"
    if hookio.grep_q(CLEAN, scan) and not hookio.grep_q(DRY_RUN, scan):
        blocked = "git clean"
    if hookio.grep_q(CHECKOUT_DDASH, scan):
        blocked = "git checkout <path>"
    if hookio.grep_q(CHECKOUT_DOT, scan):
        blocked = "git checkout <path>"

    if blocked != "":
        ev.warn(MESSAGE % blocked)
        return hookio.DENY
    return hookio.ALLOW
