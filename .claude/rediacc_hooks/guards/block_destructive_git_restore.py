"""Block the git commands that DISCARD uncommitted work: `git checkout <path>`, `git restore`, `git stash`, `git clean`, and the forced and index-rewriting forms the 2026-10-09 widenings name below.

WHY. This checkout is shared by several live sessions and the deliverable is an UNCOMMITTED working tree, so there is no safety net underneath these. They do not undo "your" change to a file, they discard every uncommitted change to it, including work you cannot see and did not write.

WHY A HOOK AND NOT A RULE. CLAUDE.md session default 1 has said "never checkout/restore/stash/clean to undo your own mistake" for months, in the same paragraph that says the tree usually holds other sessions' work. On 2026-08-14 a locale writer read that rule, then ran `git checkout --` on a single file to tidy up something a script had touched, and destroyed another session's
uncommitted value in it. The rule was not misunderstood; it was not recalled at the one second it mattered. That is what a hook is for.

THE PART THAT MAKES THIS CLASS SILENT, and why the block is worth the friction: the writer then checked `git status`, saw the file CLEAN, and sincerely reported "touched then restored, net no-op". After an unwanted edit, clean vs HEAD is the WRONG target. The right target is "identical to what was there before I arrived", and the two coincide only in a tree with no uncommitted
work, which is never true here. The command had reset PAST the prior state, so the file looked cleaner than correct. See docs/agent-reference/TRAPS.md, "Clean vs HEAD is the wrong baseline in a tree that was already dirty".

WHAT TO DO INSTEAD: repair forward. Edit the value back to what it should be. That keeps every other change in the file, including the ones you cannot see.
If a script touched a file you did not intend, say so and name the exact diff;
a reviewer can then decide, which is what happened above and is the only reason the byte was recoverable at all.

DELIBERATELY NOT BLOCKED, because these do not discard anything:
  - `git checkout <ref>` / `--detach <ref>` / `-b` / `-B`, and `git switch <branch>`: branch switching and creation, where `<ref>` resolves in the repository the command runs in.
    Only PATH-scoped checkout discards.
  - `git reset --soft` / `--mixed` / `git reset -- <path>`: they move HEAD or the index and leave every working-tree file as it is.
  - `git stash list` / `show`: read-only.
  - `git stash create` / `store`: `create` only writes a dangling commit object and `store` only records an existing commit in the stash reflog (`git help stash`); neither touches the working tree or the index.
  - `git clean -n` / `--dry-run`: prints what it would remove.
  - `git rm <path>` without `-f`, `git mv` without `-f`, `git checkout-index` without `-f`, and `git submodule update` / `deinit` without `--force`: git refuses each of them by itself over a modified or staged file (see THE 2026-10-09 SECOND WIDENING below for the measurement).
  - `git rm --cached <one literal path>`: it stages one deletion and keeps the file on disk, and git refuses it when the staged content differs from both HEAD and the file.
The escape for a genuine need is a human: ask the operator, who can run it themselves with the `!` prefix and knows what else is in the tree.

NO CROSS-TALK with block-protected-files.sh, which blocks restore/checkout/rm aimed at the hook files specifically. This guard is about the shared tree in general; that one is about protecting the guards themselves. Both may match a single command, which is fine: the first to fire wins and both messages are true.

THE 2026-10-09 WIDENING (#18c7e53c, operator ruling 2026-10-09: /branch-rebase became AI-invocable, and where something is not covered, a guard covers it instead of the skill's prose). A read-only audit drove 100 spellings through the live pre-bash chain and found these discarding forms answering rc 0: `git checkout -f [<ref>]`, `git checkout <tree-ish> <path>` without a `--`, `git checkout --ours|--theirs <path>`, `git switch -f|--discard-changes`, `git reset --hard|--merge|--keep`, and the autostash family (`--autostash` on rebase, pull and merge, `-c rebase.autoStash=true`, `git config rebase.autoStash true`). Each walked `git` command is now read by `shellscan.git_args`, the way `_destructive_clean` reads a clean, rather than by a regex over the text. The text patterns stay beside the walk, and on a command both match, the text pattern's label still names it, so every refusal recorded before this widening reads as it did.

THE 2026-10-09 SECOND WIDENING (#a234b06e). The same audit's B38-B49 still answered rc 0 after the first: `git rm -f`, `git rm --cached -r .`, `git read-tree --reset -u HEAD`, `git checkout-index -f -a`, `git submodule update --init --force` and `git submodule foreach git clean -fd`. Each decision below was measured on git 2.53.0 in a scratch repository holding a modified tracked file, a staged modification, a staged new file and an untracked file, and in a superproject whose submodule held a modified file:
  - `git rm -f` / `--force` lost the modified file; plain `git rm` refused it (rc 1, "has local modifications") and refused the staged one, and `git rm -r <dir>` left the untracked file in it alone. So `-f` is refused and plain `git rm` is not.
  - `git rm --cached -r .` (and a wildcard `--cached`) lost no file content but emptied the shared index (4 entries to 0): every peer's staged new file dropped out, and the whole tree was staged for deletion, which the next commit that reads the index (`git rebase --continue`, a merge commit, `--amend`) records. A `--cached` that is recursive, carries a wildcard or pathspec magic, or reads `--pathspec-from-file` is refused; one literal path stages one deletion and is not.
  - `git read-tree` replaces the shared index wholesale, and with `-u` the work tree too: `--reset -u HEAD` lost the modified and the staged file, and so did `-m -u HEAD`, so `-u` is no protection. No session flow runs it (neither /branch-rebase nor /pr-merge does), and the index-only spelling a session needs is `git reset`. Refused unless it is `-n`/`--dry-run`, or writes `--index-output=<file>` without `-u`.
  - `git checkout-index -f` lost the modified file; without `-f` git skipped it ("already exists", rc 1). `-f` is refused unless `--temp` or a `--prefix` outside the repository sends the files elsewhere, which is the documented export idiom.
  - `git mv -f` lost the modified destination; plain `git mv` refused ("destination exists", rc 128). The class sibling found by this sweep.
  - `git submodule update --force` / `-f` and `git submodule deinit -f` lost the submodule's modified file; without it git refused (rc 1 and rc 128). The script's own loop reads `-f|--force` by exact spelling and only before the first operand (`--forc` and `update sm --force` are usage errors that run nothing), and the guard reads it the same way. `git submodule--helper update|deinit`, the parse-options helper the script calls, takes the same `--force` and is read by git's prefix rules.
  - `git submodule foreach <command>` runs `<command>` in every submodule, so the payload is judged as a command run in each submodule the repository lists (`.gitmodules`, nested ones too under `--recursive`), by this whole guard. `foreach git clean -fd` deleted the submodule's untracked file and `foreach git checkout -- .` its modified one. A `foreach --` is a usage error and runs nothing.
  Every one of them is also judged under `git -C <sm>` and behind a `cd`, because the walk resolves the repository each command runs in.

A LONE CHECKOUT OPERAND IS A PATH UNTIL IT RESOLVES AS A REF, and that is the fail-closed direction on purpose. git itself reads `git checkout X` as a branch or commit when X resolves, then as a remote-tracking branch to create when exactly that name exists under `refs/remotes/<remote>/`, and otherwise as a PATHSPEC, which overwrites every uncommitted change to the files it matches. So the guard asks the repository the command runs in (`git rev-parse --verify -q X^{commit}`, then the remote-tracking refs) and refuses whatever answers neither. The cost of a false refusal is one retyped command: a typo'd branch name that git would have rejected anyway, or a commit not yet fetched, and `git switch [--detach] X` is the spelling that never takes a path. The cost of the other direction is a peer's uncommitted file, which is why the guard does not guess.

PORT NOTE ON THE SIX SEQUENTIAL TESTS. The bash runs all six greps unconditionally and lets each one OVERWRITE `BLOCKED`, so the message names the LAST shape that matched and not the first. `git stash pop && git clean -f` is reported as `git clean`. That is behaviour, not an accident of layout, so the loop below assigns in the same order rather than returning early.
"""

import os
import pathlib
import re
import shlex

from rediacc_hooks import commit_policy, hookio, shellscan

CHAIN = "pre-bash"
ORDER = 30

# `git clean -n` and `--dry-run` PRINT what they would remove and delete nothing. Dropping the exclusion turns the one safe way to inspect the untracked set into a refusal, which is how this guard would start being routed around.
DEFECT = (
    'not shellscan.git_args("clean", commit_policy.git_split(r.argv)[2]).on("dry-run")',
    "True",
)

# Command position: line start, or after ; & | ( $( or a backtick. Flags between
# `git` and the verb (-C <path>, -c k=v) stay matched: they change where the
# command runs, not what it destroys.
GIT = hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+")

# `git restore ...` always discards (worktree by default, index with --staged).
RESTORE = GIT + hookio.rx(r"restore([{S}]|$)")

# Bare `git stash` (stashes everything) OR an explicitly mutating subcommand. `list` and `show` must NOT match, so the verb cannot be a bare wildcard: an earlier draft made it optional, which swallowed `git stash list` and the control harness caught it immediately.
STASH_BARE = GIT + hookio.rx(r"stash[{S}]*($|[;&|])")
STASH_VERB = GIT + hookio.rx(r"stash[{S}]+(push|save|pop|apply|drop|clear|branch)([{S}]|$)")

# `git clean` deletes UNTRACKED files, which in this repo includes entire packages (pkg/chunkstore is untracked in its entirety). Excluded when -n or --dry-run appears anywhere in the invocation.
CLEAN = GIT + hookio.rx(r"clean([{S}]|$)")
DRY_RUN = hookio.rx(r"(^|[{S}])(-n|--dry-run)([{S}]|$)")

# `git checkout` ONLY when path-scoped: an explicit `--`, or a `.`/`:/` pathspec. Bare `git checkout <branch>` and `-b <new>` are untouched.
CHECKOUT_DDASH = GIT + hookio.rx(r"checkout([{S}]+[^;&|]*)?[{S}]+--([{S}]|$)")
CHECKOUT_DOT = GIT + hookio.rx(r"checkout([{S}]+-[A-Za-z-]+)*[{S}]+(\.|:/)([{S}]|$)")

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

# The operator ruling every note below cites. The hook is the guarantee; the /branch-rebase prose only describes it.
RULING = (
    "Operator ruling 2026-10-09: /branch-rebase is AI-invocable, and what its prose forbids a "
    "guard refuses, because a rule in a skill is not recalled at the one second it matters "
    "and a hook is."
)

# What each widened shape adds to MESSAGE, keyed by the label `_walked_refusal` returns.
NOTES = {
    "git checkout --force": (
        "A forced checkout overwrites every modified tracked file in the tree to match the "
        "target, so it discards a peer's uncommitted work exactly as `git checkout -- .` does. "
        "Switch without it: git refuses the switch when the tree is in the way, and that "
        "refusal is the protection."
    ),
    "git checkout <tree-ish> <path>": (
        "Two operands without a `--` are a tree-ish and a pathspec (or two pathspecs): git "
        "copies the named files out of the tree-ish over the working tree, discarding what is "
        "uncommitted in them."
    ),
    "git checkout <path>": (
        "Its one operand `%(op)s` resolves neither as a commit (`git rev-parse --verify -q "
        "%(op)s^{commit}` in %(repo)s) nor as a remote-tracking branch, so git reads it as a "
        "PATHSPEC and overwrites the matching files. If a branch or commit was meant, it does "
        "not exist there yet: fetch it, or use `git switch %(op)s` / `git switch --detach "
        "%(op)s`, which never take a path."
    ),
    "git checkout --ours/--theirs": (
        "On a conflicted path this keeps ONE side and drops the other. On a submodule gitlink "
        "(`UU private/<sm>`) both sides are wrong: `--ours` drops the branch's submodule work "
        "and `--theirs` pins a commit the submodule rebase orphaned (.claude/commands/"
        "branch-rebase.md, step 3). Pick by ancestry with `git ls-files -u <path>` and "
        "`git -C <sm> merge-base --is-ancestor`, set it with `git -C <sm> checkout <sha>`, "
        "then `git add <sm>`; for a file, edit the merged result and `git add` it."
    ),
    "git switch --discard-changes": (
        "`git switch -f` and `--discard-changes` are the same discard as a forced checkout. "
        "Switch without it, or commit first."
    ),
    "git reset --hard": (
        "`--hard`, `--merge` and `--keep` move HEAD AND rewrite the working tree to match it, "
        "taking every peer's uncommitted change in the touched files with them. `--soft`, "
        "`--mixed` and `git reset -- <path>` stay allowed. Recovering a rebase from its "
        "recorded pre-rebase SHA (`git reset --hard <sha>`) is an operator `!` command, not "
        "this session's."
    ),
    "git rebase/merge/pull --autostash": (
        "`--autostash` and `rebase.autoStash` / `merge.autoStash` STASH every uncommitted "
        "change in the tree, peers' included, run the rebase or merge, and pop it back. A pop "
        "that conflicts leaves the work in a stash entry nobody is watching, which is the "
        "discard `git stash` is refused for. Refused whatever the tree holds right now; "
        "`--no-autostash` stays allowed. A dirty tree is reported by git itself: the work "
        "there is committed by its owner first."
    ),
    "git rm --force": (
        "`-f` overrides git's own up-to-date check, so a file with uncommitted or staged "
        "changes is deleted with them. Plain `git rm <path>` stays allowed: git refuses it "
        "over a modified or staged file, and that refusal is the protection."
    ),
    "git rm --cached <many>": (
        "A recursive, wildcard or file-listed `--cached` rewrites the shared index for every "
        "path it matches: each peer's staged new file drops out of it, and the matched tree is "
        "staged for deletion, which the next commit that reads the index records. "
        "`git rm --cached <one path>` stays allowed."
    ),
    "git read-tree": (
        "`git read-tree` replaces the shared index wholesale, and with `-u` the work tree "
        "too (`-m -u` included: measured, it overwrote a staged file). Unstage a path with "
        "`git reset -- <path>`; `-n` and `--index-output=<file>` without `-u` stay allowed."
    ),
    "git checkout-index --force": (
        "`-f` overwrites the tracked files that already exist with their index version. "
        "Without it git skips them, and `--temp` or a `--prefix` outside the repository "
        "writes elsewhere; those stay allowed."
    ),
    "git mv --force": (
        "`-f` overwrites an existing destination, uncommitted changes and all. Without it git "
        "refuses (`destination exists`)."
    ),
    "git submodule --force": (
        "`git submodule update --force` and `deinit --force` throw away the submodule's "
        "uncommitted changes (`git help submodule`); without it git refuses over them. "
        "`git submodule update --init --recursive`, which /pr-merge runs, stays allowed."
    ),
    "git submodule foreach": (
        "`foreach` runs its command in every submodule, so the command is judged as if run "
        "in each of them: %(inner)s"
    ),
}

# The option tables of the verbs `shellscan.GIT_VERBS` does not describe, read by `shellscan._gh_parse` in git mode so a bundle, a unique prefix and a `--no-` negation resolve the way git resolves them (`git <verb> -h` on git 2.53.0). Each pair is `(table, noneg)` in GIT_VERBS's shape.
# One `(table, noneg)` pair: long name -> (short letter, takes a value), and the names with no `--no-` form.
Spec = tuple[dict[str, tuple[str, bool | str]], frozenset[str]]

READ_TREE: Spec = (
    {
        "index-output": ("", True),
        "empty": ("", False),
        "verbose": ("v", False),
        "m": ("m", False),
        "trivial": ("", False),
        "aggressive": ("", False),
        "reset": ("", False),
        "prefix": ("", True),
        "u": ("u", False),
        "exclude-per-directory": ("", True),
        "i": ("i", False),
        "dry-run": ("n", False),
        "no-sparse-checkout": ("", False),
        "debug-unpack": ("", False),
        "recurse-submodules": ("", "opt"),
        "quiet": ("q", False),
    },
    frozenset(("m", "u", "i", "prefix", "exclude-per-directory", "index-output")),
)
CHECKOUT_INDEX: Spec = (
    {
        "all": ("a", False),
        "ignore-skip-worktree-bits": ("", False),
        "force": ("f", False),
        "quiet": ("q", False),
        "no-create": ("n", False),
        "index": ("u", False),
        "z": ("z", False),
        "stdin": ("", False),
        "temp": ("", False),
        "prefix": ("", True),
        "stage": ("", True),
    },
    frozenset(("z", "stage", "no-create")),
)
MV: Spec = (
    {
        "verbose": ("v", False),
        "dry-run": ("n", False),
        "force": ("f", False),
        "k": ("k", False),
        "sparse": ("", False),
    },
    frozenset(("k",)),
)
# `git submodule--helper update -h` / `deinit -h`: the C helper, parse-options rules.
HELPER_UPDATE: Spec = (
    {
        "force": ("f", False),
        "init": ("", False),
        "remote": ("", False),
        "recursive": ("", False),
        "no-fetch": ("N", False),
        "checkout": ("", False),
        "merge": ("m", False),
        "rebase": ("r", False),
        "reference": ("", True),
        "ref-format": ("", True),
        "dissociate": ("", False),
        "depth": ("", True),
        "jobs": ("j", True),
        "recommend-shallow": ("", False),
        "quiet": ("q", False),
        "progress": ("", False),
        "require-init": ("", False),
        "single-branch": ("", False),
        "filter": ("", True),
    },
    frozenset(),
)
HELPER_DEINIT: Spec = (
    {"force": ("f", False), "quiet": ("q", False), "all": ("", False)},
    frozenset(),
)

# The `git submodule` script's own option loops (git-submodule.sh, git 2.53.0): exact spellings only, the options end at the first operand or `--`, and any other word starting `-` is a usage error that runs nothing. The update options that take the NEXT word as their value are listed so that value is not read as the operand that ends the loop.
SUBMODULE_TOP = frozenset(("-q", "--quiet", "--cached"))
SUBMODULE_UPDATE_BOOL = frozenset(
    (
        "-q",
        "--quiet",
        "-v",
        "--verbose",
        "--progress",
        "-i",
        "--init",
        "--require-init",
        "--remote",
        "-N",
        "--no-fetch",
        "-f",
        "--force",
        "-r",
        "--rebase",
        "--dissociate",
        "-m",
        "--merge",
        "--recursive",
        "--checkout",
        "--recommend-shallow",
        "--no-recommend-shallow",
        "--single-branch",
        "--no-single-branch",
    )
)
SUBMODULE_UPDATE_VALUED = frozenset(
    ("--ref-format", "--reference", "--depth", "-j", "--jobs", "--filter")
)
SUBMODULE_UPDATE_JOINED = (
    "--ref-format=",
    "--reference=",
    "--depth=",
    "--jobs=",
    "--filter=",
    "-j",
)
SUBMODULE_DEINIT_BOOL = frozenset(("-f", "--force", "-q", "--quiet", "--all"))
FOREACH_OPTS = frozenset(("-q", "--quiet", "--recursive"))
# How deep a `foreach` inside a `foreach` payload is read before the guard stops guessing and refuses.
FOREACH_DEPTH = 3

# What makes one `git rm --cached` operand match more than one path: a glob character, or a leading `:` (pathspec magic, `:/`, `:(glob)`).
GLOB_CHARS = frozenset("*?[")


def _wide_pathspec(op):
    return op.startswith(":") or any(c in GLOB_CHARS for c in op)


# The `git reset` options parse-options accepts (git 2.53.0 `git reset -h`), for the unique-prefix rule `shellscan._lookup` documents. Only the mode options decide anything; the rest are listed so a prefix is resolved the way git resolves it.
RESET_LONG = (
    "quiet",
    "no-quiet",
    "refresh",
    "no-refresh",
    "mixed",
    "soft",
    "hard",
    "merge",
    "keep",
    "recurse-submodules",
    "no-recurse-submodules",
    "pathspec-from-file",
    "pathspec-file-nul",
    "intent-to-add",
    "patch",
    "unified",
    "inter-hunk-context",
    "end-of-options",
)
RESET_MODES = frozenset(("mixed", "soft", "hard", "merge", "keep"))
RESET_DISCARDS = frozenset(("hard", "merge", "keep"))

# The two config keys whose truth makes a rebase or merge stash the tree. Compared lowercased: git folds the section and the key name, so `rebase.AUTOSTASH` is the same key.
AUTOSTASH_KEYS = frozenset(("rebase.autostash", "merge.autostash"))
# git's false spellings for a boolean (`git config --type=bool`), plus the EMPTY value (`-c rebase.autoStash=`, measured false on git 2.53.0); anything else, including a bare `-c rebase.autoStash` with no `=`, is true.
GIT_FALSE = frozenset(("false", "no", "off", "0"))
CONFIG_KEY_VAR = re.compile(r"^GIT_CONFIG_KEY_([0-9]+)$")

# ONE WORLD, AND IT IS A FIXTURE, since #18c7e53c. A lone checkout operand is now judged by asking the repository whether it resolves as a ref, so a golden recorded against the live checkout would freeze whichever branches that machine happens to hold (`git checkout 0826-3` is a ref on a checkout that never pruned it and a pathspec everywhere else). `git-ahead` is `_build_repo`'s pinned world: local `main` and `0831-1`, with `origin/0831-1`.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
]

EDGE_CASES = [
    ("a restore", "git restore packages/cli/src/x.ts"),
    ("a bare stash", "git stash"),
    ("a mutating stash verb", "git stash pop"),
    ("a clean", "git clean -fd"),
    ("a path-scoped checkout", "git checkout -- packages/www/src/i18n/translations/de.json"),
    ("a dot pathspec checkout", "git checkout ."),
    # The read-only forms, which are the whole reason the verb cannot be a bare wildcard.
    ("stash list is read-only", "git stash list"),
    ("stash show is read-only", "git stash show"),
    ("stash create writes only a dangling commit", "git stash create"),
    ("stash store only records a commit in the reflog", "git stash store 0123abc"),
    ("a stash drop still discards", "git stash drop"),
    ("a stash clear still discards", "git stash clear"),
    ("clean -n prints what it would remove", "git clean -n"),
    ("clean --dry-run does the same", "git clean --dry-run"),
    ("branch switching is untouched", "git checkout main"),
    ("branch creation is untouched", "git checkout -b 0901-1"),
    # The last match wins, which is why the message can name `git clean`.
    ("two destructive verbs on one line", "git stash pop && git clean -fd"),
    # #18c7e53c B-1: the forced and two-operand checkouts, each refused in the repository it runs in.
    ("B1 a forced checkout", "git checkout -f"),
    ("B1 a forced checkout of a branch", "git checkout -f main"),
    ("B1 --force in a submodule", "git -C private/renet checkout --force 0123abc"),
    ("B1 a tree-ish and a path without --", "git checkout HEAD src/x.ts"),
    ("B1 a remote ref and a path without --", "git checkout origin/main src/x.ts"),
    ("B1 a lone operand that is no ref is a pathspec", "git checkout src/x.ts"),
    ("B1 a branch name that does not exist is refused, not guessed", "git checkout 0826-3"),
    ("B1 --pathspec-from-file is a path checkout", "git checkout --pathspec-from-file=list.txt"),
    ("B1 --patch is a path checkout", "git checkout -p"),
    ("B1 a forced switch", "git switch -f main"),
    ("B1 a discarding switch", "git switch --discard-changes main"),
    ("B1 a forced switch in a submodule", "git -C private/renet switch --force main"),
    # B-3: either stage of a conflicted path, the gitlink case /branch-rebase's table proves wrong.
    ("B3 --ours on a gitlink", "git checkout --ours private/renet"),
    ("B3 --theirs on a gitlink", "git checkout --theirs private/renet"),
    ("B3 --theirs on a file under -C", "git -C private/renet checkout --theirs go.mod"),
    # B-2: the resets that rewrite the working tree.
    ("B2 a hard reset", "git reset --hard"),
    ("B2 a hard reset to a ref", "git reset --hard origin/main"),
    ("B2 a hard reset by unique prefix", "git reset --har HEAD"),
    ("B2 a merge reset", "git reset --merge"),
    ("B2 a keep reset", "git reset --keep HEAD~1"),
    ("B2 a hard reset in a submodule", "git -C private/renet reset --hard origin/main"),
    ("B2 a hard reset behind a cd", "cd private/renet && git reset --hard"),
    # C-1/C-2: every way to ask for an autostash.
    ("C1 rebase --autostash", "git rebase --autostash origin/main"),
    ("C1 merge --autostash", "git merge --autostash origin/main"),
    ("C1 pull --rebase --autostash", "git pull --rebase --autostash"),
    ("C1 pull --autostash by prefix", "git pull --autos"),
    ("C1 -c rebase.autoStash=true", "git -c rebase.autoStash=true rebase origin/main"),
    ("C1 -c with the key in another case", "git -c REBASE.AUTOSTASH=yes pull --rebase"),
    ("C1 a bare -c key is true", "git -c merge.autostash merge origin/main"),
    ("C1 --config-env hides the value", "git --config-env=rebase.autostash=V rebase origin/main"),
    (
        "C1 the GIT_CONFIG_* environment",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=rebase.autoStash GIT_CONFIG_VALUE_0=true git rebase origin/main",
    ),
    # Review 72e7ac97.2/.3: GIT_CONFIG_PARAMETERS is read per key, and an empty value is git's false (measured with `git config --type=bool` on git 2.53.0).
    (
        "C1 GIT_CONFIG_PARAMETERS sets it",
        """GIT_CONFIG_PARAMETERS="'rebase.autostash'='true'" git rebase origin/main""",
    ),
    (
        "C1 a bare GIT_CONFIG_PARAMETERS key",
        """GIT_CONFIG_PARAMETERS="'Merge.AutoStash'" git merge origin/main""",
    ),
    (
        "C control: GIT_CONFIG_PARAMETERS false",
        """GIT_CONFIG_PARAMETERS="'rebase.autostash'='false'" git rebase origin/main""",
    ),
    (
        "C control: a key that only contains the word",
        """GIT_CONFIG_PARAMETERS="'foo.autostash-note'='x'" git rebase origin/main""",
    ),
    ("C control: an empty -c value", "git -c rebase.autostash= rebase origin/main"),
    ("C2 git config sets it", "git config rebase.autoStash true"),
    ("C2 git config --global sets it", "git config --global rebase.autoStash true"),
    (
        "C2 a global write from a foreign directory",
        "git -C /tmp config --global merge.autoStash on",
    ),
    ("C2 git config set", "git config set rebase.autostash true"),
    # The allow half of each widening.
    ("B control: a branch switch", "git checkout 0831-1"),
    ("B control: the previous branch", "git checkout -"),
    ("B control: a detached commit", "git checkout --detach main"),
    ("B control: a branch created from a start point", "git checkout -b 0901-2 main"),
    ("B control: a plain switch", "git switch main"),
    ("B control: a soft reset", "git reset --soft HEAD~1"),
    ("B control: a mixed reset", "git reset --mixed"),
    ("B control: a path reset only unstages", "git reset -- src/x.ts"),
    ("B control: the last reset mode wins", "git reset --hard --soft"),
    ("B control: prose about a hard reset", "echo 'never git reset --hard here'"),
    ("C control: --no-autostash", "git rebase --no-autostash origin/main"),
    ("C control: the last autostash flag wins", "git pull --autostash --no-autostash"),
    ("C control: -c with a false value", "git -c rebase.autostash=false rebase origin/main"),
    ("C control: git config set to false", "git config rebase.autoStash false"),
    ("C control: reading the key", "git config rebase.autoStash"),
    ("C control: a plain rebase", "git rebase origin/main"),
    # #a234b06e: the second widening, refuse half (audit B38, B39, B45, B46, B48, B49 and their siblings).
    ("B38 a forced rm", "git rm -f packages/cli/x.ts"),
    ("B38 a forced recursive rm in a submodule", "git -C private/renet rm -rf pkg"),
    ("B39 a recursive cached rm", "git rm --cached -r ."),
    ("B39 a wildcard cached rm", "git rm --cached '*.ts'"),
    ("B39 a file-listed cached rm", "git rm --cached --pathspec-from-file=list.txt"),
    ("B45 a resetting read-tree", "git read-tree --reset -u HEAD"),
    ("B45 a merging read-tree with -u", "git read-tree -m -u HEAD"),
    ("B45 an index-only read-tree", "git read-tree HEAD"),
    ("B45 an emptying read-tree", "git read-tree --empty"),
    ("B46 a forced checkout-index", "git checkout-index -f -a"),
    ("B46 a forced checkout-index by prefix", "git checkout-index --forc -a"),
    ("B46 a forced checkout-index into the tree", "git checkout-index -fa --prefix=sub/"),
    ("sibling: a forced mv", "git mv -f a.txt b.txt"),
    ("B48 a forced submodule update", "git submodule update --init --force"),
    ("B48 -f on update", "git submodule --quiet update -f"),
    ("B48 a forced deinit", "git submodule deinit -f private/renet"),
    ("B48 the helper's update by prefix", "git submodule--helper update --forc"),
    ("B49 foreach clean", "git submodule foreach git clean -fd"),
    ("B49 foreach a quoted stash", "git submodule foreach 'git stash; git status'"),
    ("B49 foreach a hard reset, recursive", "git submodule foreach --recursive git reset --hard"),
    ("B49 foreach under -C", "git -C private/renet submodule foreach git checkout -- ."),
    ("B49 foreach of a foreach", "git submodule foreach git submodule foreach git clean -fd"),
    ("B49 the helper's foreach", "git submodule--helper foreach -- git clean -fd"),
    (
        "B49 a foreign foreach still writes the global config",
        "git -C /tmp submodule foreach git config --global rebase.autoStash true",
    ),
    # The allow half: git refuses each of these over uncommitted work by itself.
    ("B38 control: a plain rm", "git rm packages/cli/x.ts"),
    ("B38 control: a dry-run forced rm", "git rm -rf -n packages"),
    ("B39 control: one cached path", "git rm --cached packages/cli/x.ts"),
    ("B45 control: a dry-run read-tree", "git read-tree -n --reset -u HEAD"),
    ("B45 control: read-tree into another index file", "git read-tree --index-output=i.idx HEAD"),
    ("B46 control: checkout-index without -f", "git checkout-index -a"),
    ("B46 control: an export outside the tree", "git checkout-index -f -a --prefix=/tmp/export/"),
    ("B46 control: temp files", "git checkout-index -f --temp -a"),
    ("sibling control: a plain mv", "git mv a.txt b.txt"),
    ("B48 control: /pr-merge's update", "git submodule update --init --recursive"),
    ("B48 control: --force after an operand is a pathspec", "git submodule update x --force"),
    ("B48 control: --forc is a usage error", "git submodule update --forc"),
    ("B48 control: a plain deinit", "git submodule deinit private/renet"),
    ("B49 control: foreach a read", "git submodule foreach git status"),
    ("B49 control: foreach a fetch", "git submodule foreach 'git fetch origin --prune'"),
    ("B49 control: foreach -- is a usage error", "git submodule foreach -- git clean -fd"),
    ("B49 control: foreach a dry-run clean", "git submodule foreach git clean -n"),
    ("B49 control: a foreign foreach clean", "git -C /tmp submodule foreach git clean -fd"),
]


def _is_inside(target, root):
    """Is `target` the project tree or a path beneath it?

    Compared as resolved paths and not as strings, so `/home/x/console-2` is not read as living inside `/home/x/console`. Unresolvable answers True -- keep guarding.
    """
    try:
        t = pathlib.Path(target).resolve()
        r = pathlib.Path(root).resolve()
    except OSError:
        return True
    return t == r or r in t.parents


def _destructive_clean(cmd, scan):
    """Whether the command runs a `git clean` that deletes: each walked clean read by `shellscan.git_args("clean", ...)` (#e8be3092), so its dry run is its OWN `-n`/`--dry-run` in any spelling git accepts (`-fdn`, `--dry`) and the last of `-n`/`--no-dry-run` wins. Until 2026-10-07 a `-n` ANYWHERE on the line excused every clean: `git log -n 1 && git clean -fd` deleted with no refusal, and so did `git clean -n --no-dry-run -fd` (git 2.53.0). The text match decides only for a command whose walk places no clean."""
    cleans = commit_policy.git_runs(cmd, "clean")
    if not cleans:
        return hookio.grep_q(CLEAN, scan) and not hookio.grep_q(DRY_RUN, scan)
    return any(
        not shellscan.git_args("clean", commit_policy.git_split(r.argv)[2]).on("dry-run")
        for r in cleans
    )


def _is_ref(repo, op):
    """Whether git would read the lone checkout operand `op` as a commit or a branch to create, asked of `repo` itself. `-` is `@{-1}`, the previous branch."""
    name = "@{-1}" if op == "-" else op
    if shellscan._UNRESOLVED in name:
        return False
    if (
        commit_policy.git(["rev-parse", "--verify", "-q", "%s^{commit}" % name], cwd=repo)
        is not None
    ):
        return True
    # git's DWIM: `git checkout X` creates X from `refs/remotes/<remote>/X` when the local branch does not exist (`checkout.guess`, on by default).
    remotes = commit_policy.git(["for-each-ref", "--format=%(refname)", "refs/remotes/"], cwd=repo)
    for ref in (remotes or "").split("\n"):
        parts = ref.split("/", 3)
        if len(parts) == 4 and parts[3] == name:
            return True
    return False


def _reset_mode(args):
    """The mode a `git reset` runs in, the last mode option winning, by git's unique-prefix rule; "mixed" when none is given."""
    mode = "mixed"
    for arg in args:
        if arg == "--":
            break
        if not arg.startswith("--"):
            continue
        name = arg[2:].split("=", 1)[0]
        hits = [o for o in RESET_LONG if o == name] or [o for o in RESET_LONG if o.startswith(name)]
        if len(hits) == 1 and hits[0] in RESET_MODES:
            mode = hits[0]
    return mode


def _pull_autostash(args):
    """Whether `git pull <args>` asks for `--autostash`, the last of `--autostash`/`--no-autostash` winning, each by unique prefix (no other pull option starts `--autos` or `--no-autos`)."""
    on = False
    for arg in args:
        if arg == "--":
            break
        word = arg.split("=", 1)[0]
        if word.startswith("--autos") and "--autostash".startswith(word):
            on = True
        elif word.startswith("--no-autos") and "--no-autostash".startswith(word):
            on = False
    return on


def _truthy(value):
    """git's reading of a boolean config value: `None` is a bare key with no `=`, which is true; an empty value is false (review 72e7ac97.3)."""
    if value is None:
        return True
    word = value.strip().lower()
    return word != "" and word not in GIT_FALSE


def _params_autostash(params):
    """Whether `GIT_CONFIG_PARAMETERS` sets an autostash key true. Its entries are shell-quoted, `'key'='value'` or a bare `'key'` (the older `'key=value'` reads the same once unquoted), so each is split on its first `=` and judged like a `-c`; a value that does not parse is one git itself rejects, and is refused rather than guessed (review 72e7ac97.2: a substring test refused `'rebase.autostash'='false'` and any key containing the word)."""
    try:
        entries = shlex.split(params)
    except ValueError:
        return "autostash" in params.lower()
    for entry in entries:
        key, eq, value = entry.partition("=")
        if key.lower() in AUTOSTASH_KEYS and _truthy(value if eq else None):
            return True
    return False


def _config_autostash(globs, env):
    """Whether the git process is handed `rebase.autoStash`/`merge.autoStash` true by a `-c`, a `--config-env` (its value is not visible here, so it counts), or the `GIT_CONFIG_*` environment."""
    k = 0
    while k < len(globs):
        arg = globs[k]
        pair = None
        if arg in ("-c", "--config-env") and k + 1 < len(globs):
            pair, k = (arg, globs[k + 1]), k + 2
        elif arg.startswith("--config-env="):
            pair, k = ("--config-env", arg.split("=", 1)[1]), k + 1
        else:
            k += 1
            continue
        flag, setting = pair
        key, eq, value = setting.partition("=")
        if key.lower() in AUTOSTASH_KEYS and (
            flag == "--config-env" or _truthy(value if eq else None)
        ):
            return True
    if _params_autostash(env.get("GIT_CONFIG_PARAMETERS") or ""):
        return True
    for name, value in env.items():
        match = CONFIG_KEY_VAR.match(name)
        if (
            match
            and (value or "").lower() in AUTOSTASH_KEYS
            and _truthy(env.get("GIT_CONFIG_VALUE_%s" % match.group(1)))
        ):
            return True
    return False


def _autostash(sub, globs, args, env):
    """Whether one walked git command stashes the tree around a rebase or merge, or configures every later one to."""
    if sub == "config":
        return _config_sets_autostash(args)
    if sub not in ("rebase", "merge", "pull"):
        return False
    if _config_autostash(globs, env):
        return True
    if sub == "pull":
        return _pull_autostash(args)
    return shellscan.git_args(sub, args).on("autostash")


def _config_sets_autostash(args):
    """`git config [--global|--local|...] [set] rebase.autoStash <true>`, or `--add`/`--replace-all` of the same: a write that makes every later rebase or merge stash the tree."""
    parsed = shellscan.git_args("config", args)
    ops = list(parsed.operands)
    if ops and ops[0] in ("set", "add"):
        ops = ops[1:]
    if len(ops) < 2 or ops[0].lower() not in AUTOSTASH_KEYS:
        return False
    return ops[1].strip().lower() not in GIT_FALSE and ops[1].strip() != ""


def _checkout_refusal(args, repo, where):
    """`(label, detail)` for a walked `git checkout` that discards, else None. `where` names `repo` for the message, relative to this checkout."""
    parsed = shellscan.git_args("checkout", args)
    if parsed.on("ours") or parsed.on("theirs"):
        return "git checkout --ours/--theirs", {}
    if parsed.on("force"):
        return "git checkout --force", {}
    if "--" in args or parsed.values("pathspec-from-file") or parsed.on("patch"):
        return "git checkout <path>", None
    # Branch creation is block_second_branch's question; its one operand is a start point.
    if parsed.values("b") or parsed.values("B") or parsed.values("orphan"):
        return None
    ops = parsed.operands
    if len(ops) >= 2:
        return "git checkout <tree-ish> <path>", {}
    if len(ops) == 1 and not parsed.on("detach") and not _is_ref(repo, ops[0]):
        return "git checkout <path>", {"op": ops[0], "repo": where}
    return None


def _parse(spec, args):
    """`shellscan.ParsedArgs` for `args` against a local `(table, noneg)` pair, by git's parse-options rules."""
    table, noneg = spec
    flags, operands, _ = shellscan._gh_parse(
        list(args), table, False, git=True, noneg=noneg, problems=[]
    )
    return shellscan.ParsedArgs((), flags, operands, True)


def _rm_refusal(args):
    """The label for a walked `git rm` that discards, else None (see THE 2026-10-09 SECOND WIDENING)."""
    parsed = shellscan.git_args("rm", args)
    if parsed.on("dry-run"):
        return None
    if parsed.on("force"):
        return "git rm --force"
    if parsed.on("cached") and (
        parsed.on("r")
        or parsed.values("pathspec-from-file")
        or any(_wide_pathspec(op) for op in parsed.operands)
    ):
        return "git rm --cached <many>"
    return None


def _read_tree_refusal(args):
    """The label for a walked `git read-tree` that writes the shared index or the work tree, else None."""
    parsed = _parse(READ_TREE, args)
    if parsed.on("dry-run"):
        return None
    if parsed.values("index-output") and not parsed.on("u"):
        return None
    return "git read-tree"


def _checkout_index_refusal(args, repo):
    """The label for a walked `git checkout-index -f` that overwrites files in `repo`, else None."""
    parsed = _parse(CHECKOUT_INDEX, args)
    if not parsed.on("force") or parsed.on("temp"):
        return None
    prefix = parsed.last("prefix")
    if prefix and not commit_policy.is_inside(os.path.join(repo, prefix), repo):
        return None
    return "git checkout-index --force"


def _plain_refusal(sub, args, repo):
    """The label for a walked `git rm|read-tree|checkout-index|mv` that discards in `repo`, else None."""
    if sub == "rm":
        return _rm_refusal(args)
    if sub == "read-tree":
        return _read_tree_refusal(args)
    if sub == "checkout-index":
        return _checkout_index_refusal(args, repo)
    parsed = _parse(MV, args)
    return "git mv --force" if parsed.on("force") and not parsed.on("dry-run") else None


def _submodule_paths(repo, depth=0):
    """The submodule directories a `foreach` could visit from `repo`: every `.gitmodules` path that exists, and the nested ones too, whether or not `--recursive` was given (judging one directory too many costs nothing, and missing one is the hole)."""
    out = commit_policy.git(
        ["config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"], cwd=repo
    )
    found = []
    for line in (out or "").split("\n"):
        rel = line.split(" ", 1)[1] if " " in line else ""
        path = os.path.join(repo, rel)
        if rel and os.path.isdir(path):
            found.append(path)
            if depth < FOREACH_DEPTH:
                found.extend(_submodule_paths(path, depth + 1))
    return found


def _foreach_refusal(words, repo, root, depth):
    """`(label, note, wide)` for a `foreach` whose payload `words` discards in any submodule of `repo`, else None. `wide` is the payload's: a `git config --global` write reaches this checkout from a foreign repository's submodules too.

    The payload is judged by `_judge`, this whole guard, as a command run in each submodule directory. One payload word is a shell command line (git runs it with `sh -c`); several are an argv, re-quoted so the walk reads the same words. With no submodule present, the payload is judged in `repo` itself rather than not at all.
    """
    if not words:
        return None
    if depth >= FOREACH_DEPTH:
        return (
            "git submodule foreach",
            NOTES["git submodule foreach"]
            % {
                "inner": "a `foreach` nested this deep is not read, and is refused rather than guessed."
            },
            False,
        )
    payload = words[0] if len(words) == 1 else shlex.join(words)
    for where in _submodule_paths(repo) or [repo]:
        hit = _judge(payload, root, where, depth + 1)
        if hit is not None:
            label, note, wide = hit
            inner = "`%s` would be refused there as `%s`." % (payload, label)
            text = NOTES["git submodule foreach"] % {"inner": inner}
            return "git submodule foreach", text + ("\n\n" + note if note else ""), wide
    return None


def _submodule_refusal(sub, args, repo, root, depth):
    """`(label, note, wide)` for a walked `git submodule ...` or `git submodule--helper ...` that discards, else None; only a `foreach` payload can be wide."""
    if sub == "submodule--helper":
        verb, rest = (args[0], args[1:]) if args else ("", [])
        if verb == "update" and _parse(HELPER_UPDATE, rest).on("force"):
            return "git submodule --force", NOTES["git submodule --force"], False
        if verb == "deinit" and _parse(HELPER_DEINIT, rest).on("force"):
            return "git submodule --force", NOTES["git submodule --force"], False
        if verb == "foreach":
            words = list(rest)
            while words and words[0] != "--" and words[0].startswith("-"):
                words.pop(0)
            if words and words[0] == "--":
                words.pop(0)
            return _foreach_refusal(words, repo, root, depth)
        return None
    k = 0
    while k < len(args) and args[k] in SUBMODULE_TOP:
        k += 1
    if k >= len(args):
        return None
    verb, rest = args[k], args[k + 1 :]
    if verb == "foreach":
        j = 0
        while j < len(rest) and rest[j].startswith("-"):
            if rest[j] not in FOREACH_OPTS:
                return None  # a usage error, `--` included: git runs nothing
            j += 1
        return _foreach_refusal(rest[j:], repo, root, depth)
    if verb == "update":
        bools, valued = SUBMODULE_UPDATE_BOOL, SUBMODULE_UPDATE_VALUED
    elif verb == "deinit":
        bools, valued = SUBMODULE_DEINIT_BOOL, frozenset()
    else:
        return None
    j = 0
    while j < len(rest):
        word = rest[j]
        if word == "--" or not word.startswith("-"):
            break
        if word in ("-f", "--force"):
            return "git submodule --force", NOTES["git submodule --force"], False
        if word in valued:
            j += 2
            continue
        if word in bools or (verb == "update" and word.startswith(SUBMODULE_UPDATE_JOINED)):
            j += 1
            continue
        return None  # a usage error: git runs nothing
    return None


def _walked_refusal(cmd, root, base, depth=0):
    """`(label, note, wide)` for the last walked git command in `cmd` that discards uncommitted work in this checkout, else None.

    Each command is judged in the repository it runs in (`commit_policy.scoped_repo`); one outside this checkout is not this guard's business, and one inside it that names no repository is judged as this checkout. A `git config --global`/`--system` write is judged wherever it runs, since it reaches this checkout from anywhere.
    """
    created = commit_policy.created_dirs(cmd, base)
    found = None
    for run in commit_policy.git_runs(cmd):
        argv = run.xargv if run.xargv is not None else run.argv
        globs, sub, args = commit_policy.git_split(argv)
        if sub == "config":
            parsed = shellscan.git_args("config", args)
            wide = parsed.on("global") or parsed.on("system")
        else:
            wide = False
        repo = commit_policy.scoped_repo(run, base, root, created)
        foreign = bool(repo) and not commit_policy.is_inside(repo, root)
        # A foreign `foreach` is still read, for a payload whose write is wide; nothing else of a foreign repository is this guard's business.
        if foreign and not wide and sub not in ("submodule", "submodule--helper"):
            continue
        repo = repo or root
        where = (
            "this checkout"
            if os.path.realpath(repo) == os.path.realpath(root)
            else os.path.relpath(repo, root)
        )
        hit = None
        if _autostash(sub, globs, args, run.env):
            hit = ("git rebase/merge/pull --autostash", {})
        elif sub == "checkout":
            hit = _checkout_refusal(args, repo, where)
        elif sub == "switch":
            parsed = shellscan.git_args("switch", args)
            if parsed.on("force") or parsed.on("discard-changes"):
                hit = ("git switch --discard-changes", {})
        elif sub == "reset" and _reset_mode(args) in RESET_DISCARDS:
            hit = ("git reset --hard", {})
        elif sub in ("rm", "read-tree", "checkout-index", "mv"):
            label = _plain_refusal(sub, args, repo)
            hit = (label, {}) if label else None
        elif sub in ("submodule", "submodule--helper"):
            # Already a finished note: a foreach note carries the payload's own verdict.
            got = _submodule_refusal(sub, args, repo, root, depth)
            if got is not None and (not foreign or got[2]):
                hit, wide = (got[0], got[1]), wide or got[2]
        if hit is not None:
            found = (*hit, wide)
    if found is None:
        return None
    label, detail, wide = found
    if detail is None:
        return label, "", wide
    if isinstance(detail, str):
        return label, detail, wide
    return label, (NOTES[label] % detail if detail else NOTES[label]), wide


def _all_foreign(cmd, root, base):
    """Whether `cmd` runs at least one git invocation and every one, its own `init`/`clone` setup aside, acts outside this checkout when resolved from `base`."""
    created = commit_policy.created_dirs(cmd, base)
    runs = list(commit_policy.git_runs(cmd))
    runs = [r for r in runs if r.git_sub not in ("init", "clone")] or runs
    if not runs:
        return False
    for run in runs:
        repo = commit_policy.scoped_repo(run, base, root, created)
        if not repo or commit_policy.is_inside(repo, root):
            return False
    return True


def _judge(cmd, root, base, depth=0):
    """`(label, note, wide)` when `cmd`, run from `base`, discards uncommitted work in this checkout, else None. The whole guard: the walked check, the scope test and the text patterns, in that order. A `foreach` payload comes back through here."""
    walked = _walked_refusal(cmd, root, base, depth)
    # A user-wide or system-wide config write reaches this checkout from wherever it runs, so it is judged before the scope test below lets a foreign repository through.
    if walked is not None and walked[2]:
        return walked

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    # THIS GUARD'S ARGUMENT IS ABOUT *THIS* CHECKOUT -- that it is shared, and that a sweep here reaches another live session's uncommitted work. Neither is true of a throwaway repo a session builds under its own scratchpad, and firing there spends the guard's credibility on a command that could not harm anything: measured 2026-09-09, a writer was refused in a scratch repo by a
    # message naming twelve files in a checkout it could not reach, and worked around the guard rather than being protected by it.
    #
    # `target_root` AND NOT THE EVENT'S CWD, which was the first fix and was wrong. This harness RESETS the shell's directory after every call, so `ev.cwd` is the project directory on every invocation and a cwd test can never fire. The directory that matters is the one spelled in the COMMAND -- `git -C <dir>` or a leading `cd <dir> &&` -- which is exactly what `target_root`
    # extracts. Its own comment records this same defect being found twice before, in block-untagged-commit and block-unverified-push.
    #
    # OUTSIDE THE PROJECT TREE, not merely a different toplevel. A SUBMODULE is a different toplevel and is emphatically not foreign: private/account is shared, frozen, and full of other people's work, and a `git -C private/account add -A` is the exact sweep this guard exists to refuse. Standing down on "different toplevel" alone allowed it -- caught by asking, before shipping,
    # which repos the new predicate had just stopped protecting.
    #
    # Empty target means "this root, or unresolvable", so the guard keeps guarding by default; a resolvable target under the project directory keeps guarding too.
    #
    # RESOLVED FROM `base`, THE DIRECTORY THE COMMAND RUNS IN, as `_walked_refusal` already does. For a `foreach` payload that is the submodule, and a relative `-C` there is relative to it: `git submodule foreach git -C ../.. reset --hard` resets THIS checkout from private/renet. Resolved from the root instead, `../..` landed outside the project and the guard stood down (review 9849764b.1). At the top level `base` is the event's cwd, which this harness keeps at the project root.
    _target = shellscan.target_root(scan, base or root)
    if _target != "" and not _is_inside(_target, root):
        return None
    # FROM A CWD OUTSIDE THE PROJECT, "" IS AMBIGUOUS (review 30573c81.2): `target_root` answers "" both for the cwd's own repository and for a directory it cannot resolve. Resolving from the cwd is right, since bash runs a relative `-C` there; so the guard stands down only when EVERY git invocation resolves outside this checkout through `scoped_repo`, the rule `commit_policy.foreign_only` applies elsewhere. An outside path that neither exists nor is created by the command (an unexpanded `cd "$X"`) resolves to "" there and keeps guarding.
    if _target == "" and base and not _is_inside(base, root) and _all_foreign(cmd, root, base):
        return None

    blocked = ""
    if hookio.grep_q(RESTORE, scan):
        blocked = "git restore"
    if hookio.grep_q(STASH_BARE, scan):
        blocked = "git stash"
    if hookio.grep_q(STASH_VERB, scan):
        blocked = "git stash"
    if _destructive_clean(cmd, scan):
        blocked = "git clean"
    if hookio.grep_q(CHECKOUT_DDASH, scan):
        blocked = "git checkout <path>"
    if hookio.grep_q(CHECKOUT_DOT, scan):
        blocked = "git checkout <path>"

    if blocked != "":
        return blocked, "", False
    return walked


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    root = shellscan.repo_root_env(ev)
    hit = _judge(cmd, root, ev.field("cwd") or root)
    if hit is None:
        return hookio.ALLOW
    label, note, _wide = hit
    ev.warn(MESSAGE % label + ("\n\n" + note + "\n\n" + RULING if note else ""))
    return hookio.DENY
