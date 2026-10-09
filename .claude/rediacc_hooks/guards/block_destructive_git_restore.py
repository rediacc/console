"""Block the four commands that DISCARD uncommitted work: `git checkout <path>`, `git restore`, `git stash`, `git clean`.

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
The escape for a genuine need is a human: ask the operator, who can run it themselves with the `!` prefix and knows what else is in the tree.

NO CROSS-TALK with block-protected-files.sh, which blocks restore/checkout/rm aimed at the hook files specifically. This guard is about the shared tree in general; that one is about protecting the guards themselves. Both may match a single command, which is fine: the first to fire wins and both messages are true.

THE 2026-10-09 WIDENING (#18c7e53c, operator ruling 2026-10-09: /branch-rebase became AI-invocable, and where something is not covered, a guard covers it instead of the skill's prose). A read-only audit drove 100 spellings through the live pre-bash chain and found these discarding forms answering rc 0: `git checkout -f [<ref>]`, `git checkout <tree-ish> <path>` without a `--`, `git checkout --ours|--theirs <path>`, `git switch -f|--discard-changes`, `git reset --hard|--merge|--keep`, and the autostash family (`--autostash` on rebase, pull and merge, `-c rebase.autoStash=true`, `git config rebase.autoStash true`). Each walked `git` command is now read by `shellscan.git_args`, the way `_destructive_clean` reads a clean, rather than by a regex over the text. The text patterns stay beside the walk, and on a command both match, the text pattern's label still names it, so every refusal recorded before this widening reads as it did.

A LONE CHECKOUT OPERAND IS A PATH UNTIL IT RESOLVES AS A REF, and that is the fail-closed direction on purpose. git itself reads `git checkout X` as a branch or commit when X resolves, then as a remote-tracking branch to create when exactly that name exists under `refs/remotes/<remote>/`, and otherwise as a PATHSPEC, which overwrites every uncommitted change to the files it matches. So the guard asks the repository the command runs in (`git rev-parse --verify -q X^{commit}`, then the remote-tracking refs) and refuses whatever answers neither. The cost of a false refusal is one retyped command: a typo'd branch name that git would have rejected anyway, or a commit not yet fetched, and `git switch [--detach] X` is the spelling that never takes a path. The cost of the other direction is a peer's uncommitted file, which is why the guard does not guess.

PORT NOTE ON THE SIX SEQUENTIAL TESTS. The bash runs all six greps unconditionally and lets each one OVERWRITE `BLOCKED`, so the message names the LAST shape that matched and not the first. `git stash pop && git clean -f` is reported as `git clean`. That is behaviour, not an accident of layout, so the loop below assigns in the same order rather than returning early.
"""

import os
import pathlib
import re

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
}

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
# git's false spellings for a boolean (`git config --type=bool`); anything else, including a bare `-c rebase.autoStash`, is true.
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
    return value is None or value.strip().lower() not in GIT_FALSE


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
    params = env.get("GIT_CONFIG_PARAMETERS") or ""
    if "autostash" in params.lower():
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


def _walked_refusal(cmd, root, base):
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
        if repo and not commit_policy.is_inside(repo, root) and not wide:
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
        if hit is not None:
            found = (*hit, wide)
    if found is None:
        return None
    label, detail, wide = found
    if detail is None:
        return label, "", wide
    return label, (NOTES[label] % detail if detail else NOTES[label]), wide


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    root = shellscan.repo_root_env()
    base = ev.field("cwd") or root
    walked = _walked_refusal(cmd, root, base)
    # A user-wide or system-wide config write reaches this checkout from wherever it runs, so it is judged before the scope test below lets a foreign repository through.
    if walked is not None and walked[2]:
        ev.warn(MESSAGE % walked[0] + "\n\n" + walked[1] + "\n\n" + RULING)
        return hookio.DENY

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
    _target = shellscan.target_root(scan, shellscan.repo_root_env())
    if _target != "" and not _is_inside(_target, shellscan.repo_root_env()):
        return hookio.ALLOW

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
        ev.warn(MESSAGE % blocked)
        return hookio.DENY
    if walked is not None:
        label, note, _wide = walked
        ev.warn(MESSAGE % label + ("\n\n" + note + "\n\n" + RULING if note else ""))
        return hookio.DENY
    return hookio.ALLOW
