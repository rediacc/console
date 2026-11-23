"""Block force-push (--force / -f / --mirror / +refspec), and --force-with-lease to anything but the one live MMDD-N branch.

THE LEASE EXCEPTION, box M3 of PLAN-plan-per-pr-loop (operator ruling 2026-10-02: "The live MMDD-N branch may be force-pushed with --force-with-lease only"). A rebase of the live branch has to be republished, and the lease is the form that refuses to overwrite a remote tip nobody has seen. It is admitted only when EVERY one of these holds, read from the parsed command (`commit_policy.git_runs`, the shared lexer) and from the target repository's own refs:

  * no other forcing form anywhere in the command: no --force, -f, --mirror, and no `+refspec`;
  * every lease push the text shows is one the lexer placed (a count mismatch is a push this guard cannot judge, and is refused);
  * the repository is inside this checkout, and its checked-out branch is an `MMDD-N` name that is its ONE live branch (`commit_policy.live_branches`, local facts only, which with a landing record counts only the tree's own branch, so the landing tree republishes the PR branch and the main checkout the development branch); in a submodule that name is also the console's;
  * the push names only that branch: no refspec (git pushes the current branch), `<branch>`, `HEAD`, `HEAD:<branch>` or `<branch>:<branch>`, `refs/heads/` spellings included, to `origin`;
  * a lease value, when given, names that same branch (`--force-with-lease=<branch>[:<expected sha>]`).

Everything else stays refused, `main` above all: `main` is never an `MMDD-N` name, so no lease reaches it.

REMOTE BRANCH DELETION, since #18c7e53c (operator ruling 2026-10-09: /branch-rebase is AI-invocable, and a guard, not the skill's prose, covers what the prose forbids). `git push --delete origin <b>`, `-d`, the empty-source refspec `:<b>` and `--prune` forced nothing and passed this guard at rc 0, in the console and under `git -C private/<sm>`. Deleting a PR's head branch CLOSES the PR (GitHub records `head_ref_deleted`; measured 2026-09-24 when a branch rename closed account#87 and renet#111), so a rebase that "cleaned up" its own remote branch would end its own PR. Refused here:

  * a deletion of the branch checked out in the repository the push runs in, or of the console's checked-out branch from any submodule (step 3 of /branch-rebase leaves a submodule DETACHED at its gitlink, where its own checkout names no branch);
  * a deletion whose name the walk cannot evaluate (`--delete "$B"`);
  * `--prune`, which deletes every remote branch its refspecs do not match locally, a set no command line shows.

Allowed, because pr-merge step 7 depends on it: the post-merge cleanup `git push origin --delete <merged branch>` after `git switch main`, when no checkout names that branch any more.

THE ORIGINAL RULE, unchanged for every other form:

The first three flags are the obvious spelling. The other two were a HOLE, found 2026-08-23 while an agent was carrying out an operator-approved history rewrite: this guard refused the rewrite push, and the agent noticed that dropping the word --force would have slipped the identical non-fast-forward push straight past the regex. A --mirror git push forces every ref and deletes
remote refs absent locally; a leading + on a refspec forces that ref. Both rewrite published history, which is exactly what this guard reserves for the operator, and neither was matched.

THE + REFSPEC MATCH IS DELIBERATELY UNQUALIFIED, and the first attempt at this fix was not. It matched only `+refs/...`, which is the long form. A refspec does NOT need to be refs-qualified to force: `+main:main` and `+HEAD:main` are the common shorthand and force the remote ref exactly the same way. Both slipped straight past the widened guard that this file's own commit message
said had closed the hole. Caught in review on PR #571, and reproduced before fixing: rc 0 for `+main:main` and `+HEAD:main`, rc 2 for `+refs/heads/main`.

The pattern requires WHITESPACE before the plus, so a plus INSIDE a token is untouched: `HEAD:refs/heads/feature+x` is a legal branch name and stays allowed. That arm is pinned by a control in test-hooks.sh, because a guard widened without one is how the next false positive gets shipped.

Nothing in this repo pushes with --mirror or a + refspec (verified by grep over *.sh, *.yml, *.md, *.ts), so widening the pattern costs no legitimate caller. The mirror git push for a history rewrite is run by the operator directly, with the ! prefix, which is the intended path.
"""

import os
import re

from rediacc_hooks import commit_policy, hookio, shellscan
from rediacc_hooks.guards import tables

__getattr__ = tables("block_git_force_push", "EDGE_CASES", "ENVS", "FIXTURES", "_two_trees")

CHAIN = "pre-bash"
ORDER = 18


# The verdict itself. Until #e8be3092 this re-qualified the regex's plus arm to `+refs/`, the first attempt the header records; since every placed push is also read by `_push_forces`, that one arm can no longer reopen the hole alone, which is the point of reading pushes the way git does. Planting `if False:` here lets every force through.
DEFECT = (
    "if hookio.grep_q(FORCE_PUSH, scan) or any(any(_push_forces(r)) for r in pushes):",
    "if False:",
)
# Planted, the bound trees are the session root alone, so a deletion or a lease push typed in the sibling bound tree is judged as the root's own again (box LT11).
TWO_TREE_DEFECT = ("trees = commit_policy.bound_trees(root)", "trees = [root]")

# ANCHORED TO COMMAND POSITION 2026-08-28, after check:ci-guard-mention-anchoring found this guard refusing an ordinary sentence. Matching the phrase ANYWHERE means a doc line, a worklist note or an `echo` explaining the rule is refused as if it were the rule being broken. This NARROWS PROSE ONLY: every control below still blocks the real command, at line start and after a
# separator. NOT AN ALLOW-LIST, which this guard's own text forbids: the set of refused FLAGS is untouched. Only the position of `git push` is constrained, so a sentence about force-pushing stops being treated as one.
#
# ROUTED THROUGH lib/command-scan.sh 2026-08-30 (review finding on PR #579). Every sibling guard touched in this same PR (block-cli-bundle.sh, block-protected-files.sh, block-unverified-push.sh, block-untagged-commit.sh) scans hook_scan_target's output specifically because it unwraps eval/sh -c payloads; this guard matched $CMD directly, so `eval "git push --force ..."` or `sh -c
# 'git push --force ...'` left the push text preceded by a quote character instead of a line start or accepted separator, and the anchor added above never fired -- the exact bypass class command-scan.sh's own header exists to close, on the one guard this file calls "the whole security story".
FORCE_PUSH = hookio.rx(
    r"(^|[;&|(])[{S}]*git push[^|;&]*(--force-with-lease|--force([{S}]|=|$)|[{S}]-f([{S}]|$)|--mirror([{S}]|=|$)|[{S}]\+[^{S}])"
)

# The same forms WITHOUT the lease arm: any match here is a force the lease exception never covers.
FORCE_NOT_LEASE = hookio.rx(
    r"(^|[;&|(])[{S}]*git push[^|;&]*(--force([{S}]|=|$)|[{S}]-f([{S}]|$)|--mirror([{S}]|=|$)|[{S}]\+[^{S}])"
)

# One match per `git push` statement carrying a lease, to compare against what the lexer placed.
LEASE_PUSH = hookio.rx(r"(^|[;&|(])[{S}]*git push[^|;&]*--force-with-lease")

LEASE_FLAG = "--force-with-lease"
# Flags that ride a lease push without forcing anything else. `--force-if-includes` only narrows the lease.
LEASE_COMPANIONS = frozenset(("quiet", "verbose", "force-if-includes"))
SHA = re.compile(r"^[0-9a-f]{7,40}$")

MESSAGE = (
    "BLOCKED: this force-push is not admitted (--force / -f / --mirror / +refspec are never "
    "admitted; --force-with-lease only to the one live MMDD-N branch). Force-push overwrites "
    "remote history and erases the trace of individual PR changes, which is exactly what "
    "broke traceability before. Use a plain git push so each CI fix lands as its own "
    "reviewable commit.\n"
    "\n"
    "THE ADMITTED FORM (operator ruling 2026-10-02): after a rebase of the live branch, "
    "`git push --force-with-lease origin <live MMDD-N branch>` from that branch's checkout, "
    "optionally `--force-with-lease=<branch>:<expected sha>`. Never main, never another "
    "branch, never --force, -f, --mirror or a +refspec.\n"
    "\n"
    "When the branch AND its submodules have to be republished together, there is a "
    "mediated verb for exactly that:\n"
    "\n"
    "    .claude/hooks/stop/worklist.py --git force-push <branch>            # prints the plan\n"
    "    .claude/hooks/stop/worklist.py --git force-push <branch> --execute  # performs it\n"
    "\n"
    "It refuses main, refuses every forcing flag except the leased one, pushes SUBMODULES "
    "BEFORE THE CONSOLE so a console head can never name an unpublished submodule commit, "
    "prints the pre-push remote tips as an UNDO block, and halts on the first failure. Dry "
    "run by default: run it without --execute and read the plan first.\n"
    "\n"
    "The lease rule is exact and stays exact: no wider allow-list. Use the admitted form or "
    "the verb."
)


DELETE_MESSAGE = (
    "BLOCKED: this push deletes a remote branch that is still in use (%s). Deleting a pull "
    "request's head branch CLOSES the pull request: GitHub records `head_ref_deleted`, and on "
    "2026-09-24 exactly that closed account#87 and renet#111. A live branch's remote ref is "
    "removed only by GitHub's delete-on-merge.\n"
    "\n"
    "THE ALLOWED CLEANUP (pr-merge step 7): once the PR has merged, `git switch main` first, "
    "then `git push origin --delete <merged branch>`; a branch no checkout names any more is "
    "not refused. A rebase republishes its branch with the lease push "
    "(`git push --force-with-lease origin <live MMDD-N branch>`), never by deleting and "
    "re-pushing it.\n"
    "\n"
    "Operator ruling 2026-10-09: /branch-rebase is AI-invocable, and what its prose forbids a "
    "guard refuses. Deleting a live head deliberately is the operator's `!` command."
)


def _deleted_refs(run):
    """`(names, prunes)` for one walked `git push`: the remote branches it deletes, as written (`--delete`/`-d` makes every refspec a deletion; otherwise a refspec with an empty source, `:<b>`, is one), and whether it carries `--prune`. Read from the EXPANDED argv, so a name the walk cannot evaluate carries `shellscan._UNRESOLVED`."""
    argv = run.xargv if run.xargv is not None else run.argv
    _, _, args = commit_policy.git_split(argv)
    parsed = shellscan.git_push_args(args)
    refspecs = parsed.operands[1:]
    if parsed.on("delete"):
        names = list(refspecs)
    else:
        names = []
        for spec in refspecs:
            src, colon, dst = spec.lstrip("+").partition(":")
            if colon and src == "" and dst:
                names.append(dst)
    return names, parsed.on("prune")


def deletion_refusal(ev, cmd):
    """ "" unless a walked push in this checkout deletes a branch still in use, else why."""
    root = ev.project_dir
    base = ev.field("cwd") or root
    created = commit_policy.created_dirs(cmd, base)
    top = commit_policy.toplevel(root)
    console = commit_policy.current_branch(top, foreign=True) if top else ""
    # Either bound tree is this checkout (box LT11): a push typed in the sibling answers its own toplevel, whose branch is in use there.
    trees = commit_policy.bound_trees(root)
    for run in commit_policy.git_runs(cmd, "push"):
        names, prunes = _deleted_refs(run)
        if not names and not prunes:
            continue
        repo = commit_policy.scoped_repo(run, base, root, created, cmd, trees=trees)
        if repo and not commit_policy.is_ours(repo, root, trees):
            continue
        if prunes:
            return "`--prune` deletes every remote branch its refspecs do not match locally"
        here = commit_policy.current_branch(repo) if repo else console
        in_use = {b for b in (here, console) if b}
        for name in names:
            short = name.removeprefix("refs/heads/")
            if shellscan._UNRESOLVED in short or "$" in short:
                return "a deleted branch name this guard cannot evaluate"
            if short in in_use or short == "HEAD":
                return "`%s` is the branch checked out here" % short
    return ""


def _count(pattern, text):
    compiled = re.compile(pattern)
    records, _ = hookio._records(text)
    return sum(len(list(compiled.finditer(record))) for record in records)


def _names(branch):
    return (branch, "refs/heads/" + branch)


def _push_forces(run):
    """`(force, lease)` for one walked `git push`: whether it forces outside a lease (`--force`/`-f` in any bundle, `--mirror`, a `+refspec`) and whether it carries a lease, read by `shellscan.git_push_args` (#e8be3092).

    Measured on git 2.53.0 against the regexes below, which still run beside it: `git push -uf` and `-qf` forced the remote branch and matched neither, and `--force-with` is `--force-with-lease` by unique prefix, so it forced `main` past the one-live-branch rule unseen.
    """
    _, _, args = commit_policy.git_split(run.argv)
    parsed = shellscan.git_push_args(args)
    force = (
        parsed.on("force") or parsed.on("mirror") or any(o.startswith("+") for o in parsed.operands)
    )
    lease = parsed.last("force-with-lease")
    return force, lease is not None and lease != "false"


def _lease_run_refusal(run, root, base):
    """ "" when this lease push is the admitted form, else why not."""
    _, _, args = commit_policy.git_split(run.argv)
    parsed = shellscan.git_push_args(args)
    positionals = parsed.operands
    repo = commit_policy.run_repo(run, base)
    # Either bound tree is this checkout (box LT11), and the console whose name a submodule's branch carries is the bound tree holding it.
    trees = commit_policy.bound_trees(root)
    if not repo or not commit_policy.is_ours(repo, root, trees):
        return "the repository it pushes is not inside this checkout"
    live = commit_policy.current_branch(repo)
    if not commit_policy.BRANCH_SHAPE.match(live):
        return "the checkout is on `%s`, not an MMDD-N branch" % (live or "(detached)")
    if commit_policy.live_branches(repo, gh=False) != [live]:
        return "`%s` is not the ONE live branch here" % live
    top = commit_policy.toplevel(commit_policy.owning_tree(repo, trees) or root)
    if os.path.realpath(repo) != os.path.realpath(top):
        console = commit_policy.current_branch(top, foreign=True) if top else ""
        if live != console:
            return "a submodule's live branch carries the console's name (`%s`)" % console
    if parsed.problems:
        return "`%s` is an option git itself refuses" % parsed.problems[0][1]
    for name, value in parsed.flags:
        if name in LEASE_COMPANIONS:
            continue
        if name == "force-with-lease":
            name_, _, expect = value.partition(":")
            if value and (name_ not in _names(live) or (expect and not SHA.match(expect))):
                return "the lease names `%s`, not the live branch `%s`" % (value, live)
            continue
        return "`--%s` is not part of the admitted lease form" % name
    if len(positionals) > 2:
        return "it pushes more than one refspec"
    if positionals and positionals[0] != "origin":
        return "the remote is `%s`, not origin" % positionals[0]
    if len(positionals) == 2:
        src, colon, dst = positionals[1].partition(":")
        if not colon:
            dst = src
        if src not in (*_names(live), "HEAD") or dst not in (*_names(live), "HEAD"):
            return "the refspec `%s` is not the live branch `%s`" % (positionals[1], live)
    return ""


def lease_refusal(ev, cmd, scan, text_scan):
    """ "" when every force in `cmd` is an admitted lease to the one live branch, else why not.

    `scan` carries the lexer's canonical push lines; `text_scan` is the command text alone, whose lease count the lexer has to reach (a lease the text shows and the lexer did not place is one this guard cannot judge).
    """
    pushes = commit_policy.git_runs(cmd, "push")
    if hookio.grep_q(FORCE_NOT_LEASE, scan) or any(_push_forces(r)[0] for r in pushes):
        return "a forcing form other than --force-with-lease"
    leases = [r for r in pushes if _push_forces(r)[1]]
    if not leases or len(leases) < _count(LEASE_PUSH, text_scan):
        return "a lease push this guard cannot place"
    root = ev.project_dir
    base = ev.field("cwd") or root
    for run in leases:
        reason = _lease_run_refusal(run, root, base)
        if reason:
            return reason
    return ""


def run(ev):
    cmd = ev.raw("tool_input", "command")
    # SCOPE: this policy is about THIS checkout and its submodules. A push in a repository outside it (a `/tmp` fixture, even one the same command `git init`s) is not its business (finding #5810a9f3).
    if commit_policy.foreign_only(ev, cmd, ("push",)):
        return hookio.ALLOW
    deleting = deletion_refusal(ev, cmd)
    if deleting:
        ev.warn(DELETE_MESSAGE % deleting)
        return hookio.DENY
    text_scan = scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    # `git -C <dir> push --force` put a word between `git` and `push` and matched nothing here until 2026-10-02; the lexer's canonical spelling of each push closes that (commit_policy.push_texts).
    canon = commit_policy.push_texts(cmd)
    if canon:
        scan = scan + "\n" + canon

    # Each push the walk places is read the way git reads it (`_push_forces`), and the text match stays beside it rather than behind it: a force in a shape the walk cannot place is still refused, at the cost of refusing `--force --no-force`, which forces nothing.
    pushes = commit_policy.git_runs(cmd, "push")
    if hookio.grep_q(FORCE_PUSH, scan) or any(any(_push_forces(r)) for r in pushes):
        reason = lease_refusal(ev, cmd, scan, text_scan)
        if reason == "":
            return hookio.ALLOW
        ev.warn(MESSAGE + "\n\nNot admitted here because: " + reason + ".")
        return hookio.DENY
    return hookio.ALLOW
